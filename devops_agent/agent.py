# devops_agent/agent.py
"""
Agent Orchestrator

This is the central coordinator that manages the entire flow:
1. Takes user query in natural language
2. Asks LLM to select appropriate tool(s) and parameters
3. Applies safety checks for dangerous operations
4. Executes the tool(s) via MCP client (supports parallel execution)
5. Formats and returns the result(s) to the user
"""

# Import required modules from our project
from .llm.ollama_client import get_tool_calls, ensure_model_exists
from .mcp.client import call_tool_async, test_connection, test_k8s_connection, test_remote_k8s_connection
# [PHASE 6] Safety checks via analyze_risk are imported inline where needed
from .tools import get_tools_schema
from .k8s_tools import get_k8s_tools_schema
from .k8s_tools.remote_k8s_tools import get_remote_k8s_tools_schema
from typing import Dict, Any, List, Optional
from .settings import settings
import asyncio
from .context_cache import context_cache

# In-memory buffer for slow query logging (flushed periodically)
_SLOW_QUERY_BUFFER = []
_SLOW_QUERY_BUFFER_SIZE = 10

def _log_slow_query(timestamp: str, query: str):
    """Non-blocking slow query logger. Buffers writes to avoid disk I/O in hot path."""
    global _SLOW_QUERY_BUFFER
    _SLOW_QUERY_BUFFER.append(f"{timestamp} | {query}\n")
    
    # Flush when buffer reaches threshold
    if len(_SLOW_QUERY_BUFFER) >= _SLOW_QUERY_BUFFER_SIZE:
        _flush_slow_query_buffer()

def _flush_slow_query_buffer():
    """Flush buffered slow queries to disk."""
    global _SLOW_QUERY_BUFFER
    if not _SLOW_QUERY_BUFFER:
        return
    try:
        with open("devops_agent/data/slow_queries.log", "a", encoding="utf-8") as f:
            f.writelines(_SLOW_QUERY_BUFFER)
        _SLOW_QUERY_BUFFER = []
    except Exception:
        pass

_CACHED_AGENT = None

def process_query(query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Process a user's natural language query and return result with metadata.
    Returns: {"output": str, "tool_calls": List[dict]}
    """
    return asyncio.run(process_query_async(query, history))

async def process_query_async(query: str, history: Optional[List[Dict[str, str]]] = None, log_callback=None, session_id: str = None, forced_mcps: List[str] = None) -> Dict[str, Any]:
    """
    Async implementation of query processing with parallel tool execution.
    Returns: {"output": str, "tool_calls": List[dict]}
    """
    # [PHASE 3] Speculative State
    speculative_task = None
    speculative_tool = None
    speculative_args = None
    
    # [PHASE 4] Intent Analysis for Adaptive Intelligence
    raw_keywords = ["all", "full", "unfiltered", "entire", "every"]
    insight_keywords = ["why", "compare", "is it", "difference", "risk", "opinion", "same as", "better"]
    
    query_lower = query.lower()
    is_raw_override = any(k in query_lower for k in raw_keywords)
    is_insight_intent = any(k in query_lower for k in insight_keywords)
    compression_mode = "RAW" if is_raw_override else "COMPRESSED"

    # Ensure background pulse is running for live context
    from .pulse import get_pulse
    pulse = get_pulse()
    if not pulse._running:
        asyncio.create_task(pulse.start())

    # Schema loading moved to Lazy Load block (see below)
    
    # 2. Ask DSPy Agent to choose tool(s)
    # Lazy initialization of DSPy (if not already done)
    # In a production app, we might do this at startup.
    # 2. Ask DSPy Agent to choose tool(s)
    # Lazy initialization of DSPy (if not already done)
    # In a production app, we might do this at startup.
    from .dspy_client import init_dspy_lms
    from .agent_module import DevOpsAgent, parse_dspy_tool_calls
    
    # [PHASE 5] Semantic Intent Router (Layered Cascade)
    # Check for instant matches BEFORE loading heavy agent models or fetching context
    from .router import get_router
    router = get_router()
    
    instant_tools = router.route(query)
    
    # [OPTIMIZATION] Layer 1.5 Semantic Cache
    from .context_cache import get_context_cache
    from .pulse import get_pulse
    from .semantic_cache import get_semantic_cache
    sem_cache = get_semantic_cache()
    cached_result = None
    if not instant_tools:
        # Check if we've answered this (or something very similar) before
        # We pass the currently active MCP domain from context if available
        active_mcp = context_cache.get_last_mcp(session_id)
        cached_result = await sem_cache.lookup(query, active_mcp=active_mcp)
        
    if instant_tools:
        msg = f"⚡ [IntentRouter] Bypassing Agent for instant match."
        print(msg)
        if log_callback: log_callback("thought", msg)
        
        # We skip directly to execution (Step 3)
        tool_calls = instant_tools
    if not instant_tools and not cached_result:
        # Initialize both LMs (Fast and Smart)
        # This ensures we have the right context objects
        import dspy
        try:
             # Double check if already configured to avoid re-init cost? 
             # dspy.settings.lm is global. 
             # But we need the specific instances for context switching.
             # So we call our helper which returns them (cached ideally, but cheap enough)
             fast_lm, smart_lm = init_dspy_lms()
        except Exception as e:
             print(f"⚠️ Failed to init DSPy LMs: {e}")
             fast_lm, smart_lm = None, None
             
    if not instant_tools and not cached_result:
        # [LAYER 5] Continuous Optimization Logging (Async to avoid latency impact)
        # Log queries that required LLM (Slow Path) so we can optimize them later
        # Note: Logging is now async and non-blocking
        import datetime
        _log_slow_query(datetime.datetime.now().isoformat(), query)

        # [LAZY LOAD TOOLS]
        # Only load tool definitions if we need the LLM
        try:
            # [PHASE 5] RAG Tool Selection (Layer 4)
            from .rag.tool_retriever import get_retriever
            retriever = get_retriever()
            relevant_tools = await retriever.retrieve(query, top_k=8)
            all_tools_schema = relevant_tools
            if log_callback: log_callback("thought", f"🔍 [RAG] Selected {len(relevant_tools)} relevant tools (Context Optimization).")
            # Define relevant_mcps for speculative logic below even if RAG succeeds
            relevant_mcps = ["docker", "k8s_local", "k8s_remote"] 
        except Exception as e:
            # Fallback to loading all tools (Smart Filtered)
            if log_callback: log_callback("debug", f"⚠️ RAG failed ({e}), loading tools via Smart Router.")
            
            # [PHASE 8 & 9] Smart MCP Routing with Override
            from .smart_router import smart_router
            
            if forced_mcps:
                relevant_mcps = forced_mcps
                if log_callback: log_callback("thought", f"🔒 Forced MCP Mode: {relevant_mcps}")
            else:
                # [PHASE 10] Pass session_id for context-aware routing
                relevant_mcps = smart_router.route(query, session_id=session_id)
                if log_callback: log_callback("thought", f"🧠 Smart Router selected MCPs: {relevant_mcps}")

            # [PHASE 3] Speculative Resource Prefetching
            # If user mentions a specific pod/container, start fetching its details in background
            import re
            potential_resource = re.search(r'(?:pod|container|deployment|node)\s+([\w-]+)', query, re.I)
            if potential_resource:
                res_name = potential_resource.group(1)
                # If we have a clear target, speculatively fetch its status
                if "pod" in query.lower():
                    speculative_tool = "remote_k8s_describe_pod" if "remote" in query.lower() else "local_k8s_describe_pod"
                    speculative_args = {"name": res_name}
                    if log_callback: log_callback("thought", f"⚡ Speculatively pre-fetching details for pod: {res_name}")
                    speculative_task = asyncio.create_task(call_tool_async(speculative_tool, speculative_args))
            
            all_tools_schema = []
            
            # Smart Load (Using smart_router as it was imported in the except block)
            from .smart_router import smart_router 
            if "docker" in relevant_mcps:
                all_tools_schema.extend(get_tools_schema())
                
            if "k8s_local" in relevant_mcps:
                from .k8s_tools import get_local_k8s_tools_schema
                all_tools_schema.extend(get_local_k8s_tools_schema())
                
            if "k8s_remote" in relevant_mcps:
                all_tools_schema.extend(get_remote_k8s_tools_schema())
                
            # [CHAT OPTIMIZATION]
            has_memory = False
            if session_id:
                if context_cache.get_context_block(session_id):
                    has_memory = True
            
            if "chat" in relevant_mcps or not all_tools_schema or has_memory:
                from .tools.chat_tool import ChatTool
                chat_tool_schema = {
                   "name": ChatTool.name,
                   "description": ChatTool.description,
                   "parameters": ChatTool().get_parameters_schema()
                }
                if not any(t['name'] == 'chat' for t in all_tools_schema):
                   all_tools_schema.append(chat_tool_schema)

        # Instantiate the agent (ReAct / CoT) with dual models
        # [OPTIMIZATION] Use cached agent to avoid reloading compiled program from disk every time
        global _CACHED_AGENT
        if _CACHED_AGENT is None:
            agent = DevOpsAgent(fast_lm=fast_lm, smart_lm=smart_lm)
            _CACHED_AGENT = agent
        else:
            # Update LMs just in case they changed (usually they are singletons too)
            agent = _CACHED_AGENT
            agent.fast_agent.lm = fast_lm
            agent.smart_lm = smart_lm
        import time
        t_start = time.time()
        
        # --- RICH CONTEXT: STATE INJECTION ---
        # Fetch live state to help the agent verify resource names
        pulse = get_pulse()
        context_str = pulse.get_summary_block()
        
        # Add short-term memory if available
        if session_id:
            memory = context_cache.get_context_block(session_id)
            if memory:
                context_str += "\n\n" + memory

        try:
            t_ctx_start = time.time()
            if log_callback: log_callback("thought", "🔍 Analyzing context intent...")

            # Smart Context: Only fetch relevant context based on query intent
            # This reduces unnecessary latency and failures (e.g. if remote is offline but user wants docker)
            q_lower = query.lower().strip()
            
            # SKIP context for conversational queries to improve speed
            chat_keywords = ["hi", "hello", "hey", "help", "who are you", "what is this", "thanks", "thank you", "bye", "test"]
            is_chat = any(q_lower == w or q_lower.startswith(w + " ") for w in chat_keywords)
            
            want_remote = False
            want_local_k8s = False
            want_docker = False
            
            if not is_chat:
                # [OPTIMIZATION] Skip remote if pulse shows it's down
                remote_status = pulse.get_status("k8s_remote").get("status")
                want_remote = ("remote" in q_lower or "node" in q_lower) and remote_status != "disconnected"
                
                want_local_k8s = "local" in q_lower or "pod" in q_lower or "deployment" in q_lower or "service" in q_lower
                want_docker = "docker" in q_lower or "container" in q_lower
                
                # If query is generic but not chat, we might want to fetch everything or nothing.
                # Let's say if no specific intent, we default to fetching local k8s + docker for speed, 
                # and skip remote unless explicitly asked (as remote can be slow).
                if not (want_remote or want_local_k8s or want_docker):
                     # Check for generic "list" or "status" commands that imply intent
                     if "list" in q_lower or "get" in q_lower or "show" in q_lower:
                         want_local_k8s = True

                
            ctx_tasks = []
            task_map = {} # Map index to type
            
            if want_docker:
                if log_callback: log_callback("thought", "🐳 Context: Docker")
                ctx_tasks.append(call_tool_async("docker_list_containers", {"all": False}))
                task_map[len(ctx_tasks)-1] = "docker"
                
            if want_local_k8s:
                if log_callback: log_callback("thought", "☸️ Context: K8s Local")
                ctx_tasks.append(call_tool_async("local_k8s_list_pods", {"namespace": "default"}))
                task_map[len(ctx_tasks)-1] = "local_k8s"
                
            if want_remote:
                if log_callback: log_callback("thought", "☁️ Context: K8s Remote")
                ctx_tasks.append(call_tool_async("remote_k8s_list_nodes", {}))  # Get Remote Nodes
                task_map[len(ctx_tasks)-1] = "remote_k8s"

            if ctx_tasks:
                if log_callback: log_callback("thought", "⏳ Fetching live context...")
                # TIMEOUT: Use configurable timeout
                ctx_results = await asyncio.wait_for(
                    asyncio.gather(*ctx_tasks, return_exceptions=True), 
                    timeout=settings.CONTEXT_TIMEOUT
                )
                
                # Parse Results based on what we requested
                containers = []
                pods = []
                nodes = []
                
                for i, res in enumerate(ctx_results):
                    t_type = task_map.get(i)
                    
                    if isinstance(res, dict) and res.get("success"):
                        if t_type == "docker":
                            containers = [c["name"] for c in res.get("containers", [])]
                        elif t_type == "local_k8s":
                            pods = [p["name"] for p in res.get("pods", [])]
                        elif t_type == "remote_k8s":
                            nodes = [n["name"] for n in res.get("nodes", [])]
                    elif isinstance(res, Exception):
                         # Log individual task failure but don't fail whole context
                         print(f"   [Context] Task {t_type} failed: {res}")

                context_parts = []
                if containers:
                    context_parts.append(f"Running Containers: {', '.join(containers)}")
                if pods:
                    context_parts.append(f"Active Pods (Default): {', '.join(pods)}")
                if nodes:
                    context_parts.append(f"Available Nodes (Remote): {', '.join(nodes)}")
                    
                if context_parts:
                    context_str = "\n[System Context: " + " | ".join(context_parts) + "]"
                    # print(f"🔎 Injected Context: {context_str}")
                    if log_callback: log_callback("thought", f"🔎 Injected Context: {len(context_parts)} source(s)")
                
                # print(f"⏱️ [PERF] Context Injection: {time.time() - t_ctx_start:.2f}s")
                
        except asyncio.TimeoutError:
             print(f"⚠️  Context injection timed out after {settings.CONTEXT_TIMEOUT}s (proceeding without it)")
             if log_callback: log_callback("thought", f"⚠️ Context timeout ({settings.CONTEXT_TIMEOUT}s)")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️  Context injection failed (skipping): {str(e)}")
            # Only print traceback if debug needed, or if error message is empty
            if not str(e):
                 print(f"   [Debug] No error message. Traceback:\n{error_details}")

        # Inject context into query
        
        # [SMART CONTEXT] Inject Memory
        memory_block = context_cache.get_context_block(session_id)
        memory_context_str = ""
        if memory_block:
            memory_context_str = f"\n[Working Memory (Recent Observations)]:\n{memory_block}\nINSTRUCTION: Check the Working Memory above. If it contains the answer, reply directly using 'chat'. Only call a tool if the information is MISSING or the user explicitly requests a fresh check.\n"
            if log_callback: log_callback("thought", "🧠 Using Working Memory context")
        
        full_query = query + context_str + memory_context_str if (context_str or memory_context_str) else query

        # print(f"🧠 DSPy Agent Thinking... (Query: {full_query})")
        if log_callback: log_callback("thought", "🧠 Agent reasoning...")
        
        try:
            t_agent_start = time.time()
            prediction = agent(query=query, tools_schema=all_tools_schema, history=history, log_callback=log_callback)
            print(f"⏱️ [PERF] Agent Inference: {time.time() - t_agent_start:.2f}s")
            
            # Extract the tool_calls from the prediction
            # dspy.ChainOfThought puts the reasoning in `prediction.reasoning`
            # and the output field in `prediction.tool_calls`
            raw_tool_calls = prediction.tool_calls
            # print(f"🐛 DSPy Raw Output: {raw_tool_calls}")
            
            # print(f"[DEBUG] agent.py: Calling parse_dspy_tool_calls...")
            tool_calls = parse_dspy_tool_calls(raw_tool_calls)
            # print(f"[DEBUG] agent.py: Parsed tool_calls: {tool_calls}")
            
        except Exception as e:
            print(f"❌ DSPy Execution Error: {e}")
            if log_callback: log_callback("error", f"DSPy Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "output": f"❌ Brain freeze! The agent encountered an error: {e}",
                "tool_calls": []
            }
    
    if cached_result:
        # Fast exit with cached data
        if log_callback: log_callback("thought", "⚡ [SemanticCache] Blistering fast retrieval active.")
        return cached_result

    if not tool_calls:
        return {
            "output": "❌ I couldn't understand that request or map it to a valid tool. Please try again.",
            "tool_calls": []
        }
    
    # --- DISAMBIGUATION CHECK ---
    # --- DISAMBIGUATION CHECK ---
    # Define ambiguous tool pairs (tool_name -> alternative_tool_name)
    # We map both directions so we catch the LLM regardless of which one it randomly picks
    AMBIGUOUS_TOOL_PAIRS = {
        # Local -> Remote
        "local_k8s_list_pods": "remote_k8s_list_pods",
        "local_k8s_list_nodes": "remote_k8s_list_nodes",
        "local_k8s_list_deployments": "remote_k8s_list_deployments",
        "local_k8s_describe_node": "remote_k8s_describe_node",
        "local_k8s_describe_deployment": "remote_k8s_describe_deployment",
        "local_k8s_describe_pod": "remote_k8s_describe_pod",
        
        # Remote -> Local
        "remote_k8s_list_pods": "local_k8s_list_pods",
        "remote_k8s_list_nodes": "local_k8s_list_nodes",
        "remote_k8s_list_deployments": "local_k8s_list_deployments",
        "remote_k8s_describe_node": "local_k8s_describe_node",
        "remote_k8s_describe_deployment": "local_k8s_describe_deployment",
        "remote_k8s_describe_pod": "local_k8s_describe_pod",
    }
    
    # Check if query explicitly mentions "remote" or "local"
    query_lower = query.lower()
    is_explicit_remote = "remote" in query_lower
    is_explicit_local = "local" in query_lower
    
    # Analyze Session Context (Sticky Mode)
    # We look at previous assistant tool calls to determine the "mode" of the session.
    session_has_remote = False
    session_has_local = False
    
    if history:
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # Check for tool usage in assistant messages
            if role == "assistant":
                if "remote_k8s_" in content:
                    session_has_remote = True
                if "local_k8s_" in content: # local tools
                    # exclude the ambiguous ones from counting as 'local' evidence if they were auto-selected by LLM?
                    # actually, if we successfully ran a local tool, it counts.
                    if "remote_k8s_" not in content:
                        session_has_local = True
            
            # Also check user intent in user messages
            if role == "user":
                if "remote" in content.lower():
                    session_has_remote = True
                if "local" in content.lower():
                    session_has_local = True

    # Determine strong context
    # If we have ONLY remote usage -> Default Remote
    # If we have ONLY local usage -> Default Local
    # If we have BOTH or NEITHER -> Ambiguous/Mixed
    strong_remote_context = session_has_remote and not session_has_local
    strong_local_context = session_has_local and not session_has_remote
    
    # Modify tool calls based on context
    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        
        # Is this an ambiguous tool?
        if tool_name in AMBIGUOUS_TOOL_PAIRS:
            alternative_tool = AMBIGUOUS_TOOL_PAIRS[tool_name]
            
            # Determine which is Remote and which is Local
            if "remote_" in tool_name:
                remote_tool = tool_name
                local_tool = alternative_tool
            else:
                remote_tool = alternative_tool
                local_tool = tool_name

            # CASE 1: Explicit Remote in Query -> FORCE REMOTE
            if is_explicit_remote:
                if tool_name != remote_tool:
                    print(f"🔄 Auto-switching {tool_name} -> {remote_tool} (Explicit 'remote' in query)")
                    tool_calls[i]["name"] = remote_tool
                continue
                
            # CASE 2: Explicit Local in Query -> FORCE LOCAL
            if is_explicit_local:
                if tool_name != local_tool:
                    print(f"🔄 Auto-switching {tool_name} -> {local_tool} (Explicit 'local' in query)")
                    tool_calls[i]["name"] = local_tool
                continue

            # CASE 3: Strong Remote Context -> AUTO SWITCH TO REMOTE
            if strong_remote_context:
                if tool_name != remote_tool:
                    print(f"🔄 Auto-switching {tool_name} -> {remote_tool} (Sticky Session Context: REMOTE)")
                    tool_calls[i]["name"] = remote_tool
                continue

            # CASE 4: Strong Local Context -> AUTO SWITCH TO LOCAL
            if strong_local_context:
                if tool_name != local_tool:
                    print(f"🔄 Auto-switching {tool_name} -> {local_tool} (Sticky Session Context: LOCAL)")
                    tool_calls[i]["name"] = local_tool
                continue
                
            # CASE 5: Default to REMOTE (per user config)
            # If we are here, there is NO explicit context. 
            # We used to ask, but now we default to Remote as it's the primary use case.
            if tool_name != remote_tool:
                 print(f"🔄 Auto-switching {tool_name} -> {remote_tool} (Default: Remote)")
                 tool_calls[i]["name"] = remote_tool
            continue

    
    # 3. Plan execution
    tasks = []
    
    # Check if we should use web-based confirmation flow (passed via kwargs or implied by log_callback presence?)
    # Ideally simpler: allow process_query_async to accept a flag.
    # We will assume if "log_callback" is present, we are in Web/API mode, thus we want to request confirmation 
    # rather than failing or blocking on stdin.
    is_web_mode = log_callback is not None

    from .safety import analyze_risk

    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]
        
        # [PHASE 6] Non-Blocking Safety Check
        risk = analyze_risk(tool_name, arguments)
        
        if risk.is_dangerous:
            # We PAUSE execution and return a request for confirmation
            # This works for both Web (Card) and CLI (Prompt) which handle the event
            return {
                "output": f"⚠️ Action requires approval: {tool_name}",
                "tool_calls": tool_calls, # Return original plan so we can resume? Actually we just need this one info
                "confirmation_request": {
                    "tool": tool_name,
                    "arguments": arguments,
                    "risk": risk.to_dict()
                }
            }
        
        print(f"[INFO] Scheduling tool {index + 1}/{len(tool_calls)}: {tool_name}")
        
        # [PHASE 3] Speculative Injection
        if speculative_task and tool_name == speculative_tool and arguments == speculative_args:
            print(f"🚀 [Speculative] Re-using pre-fetched result for {tool_name}!")
            tasks.append((index, tool_name, speculative_task))
        else:
            tasks.append((index, tool_name, call_tool_async(tool_name, arguments)))
    
    if not tasks:
        if tool_calls and len(tasks) == 0:
            return {
                "output": "❌ All operations cancelled (or pending confirmation).",
                "tool_calls": tool_calls
            }
        return {
            "output": "⚠️  No valid tools identified.",
            "tool_calls": tool_calls
        }

    # 4. Execute tool calls in parallel
    coroutines = [t[2] for t in tasks]
    results = await asyncio.gather(*coroutines)
    
    # 5. Format results keeping original order
    execution_results = {}
    for i, res in enumerate(results):
        original_idx = tasks[i][0]
        tool_name = tasks[i][1]
        execution_results[original_idx] = (tool_name, res)
        
    final_output_lines = []
    
    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        
        if i in execution_results:
            _, result = execution_results[i]
            
            # [BATCH DESCRIBE] Post-Processor - Parallel Describe Orchestration
            if tool_call.get("_batch_describe") and result.get("success"):
                batch_result = await _execute_batch_describe(
                    result=result,
                    resource_type=tool_call.get("_batch_resource_type", "pod"),
                    prefix=tool_call.get("_batch_prefix", "remote_k8s_"),
                    full_detail=tool_call.get("_batch_full_detail", False),
                    namespace=tool_call.get("arguments", {}).get("namespace", "default"),
                    log_callback=log_callback
                )
                if batch_result:
                    result = batch_result  # Replace with batch result
            
            # [SMART CONTEXT] Auto-Memorize
            if session_id:
                try:
                    entities = _extract_entities_from_result(tool_name, result)
                    if entities:
                        context_cache.update(session_id, entities)
                        
                    # [PHASE 10] Update Last Active MCP
                    # Map tool name -> MCP ID
                    active_mcp = None
                    if "docker" in tool_name: active_mcp = "docker"
                    elif "local_k8s" in tool_name: active_mcp = "k8s_local"
                    elif "remote_k8s" in tool_name: active_mcp = "k8s_remote"
                    
                    if active_mcp:
                        context_cache.set_last_mcp(session_id, active_mcp)

                except Exception as ex:
                    print(f"Failed to update memory: {ex}")

            from .formatters import FormatterRegistry
            formatted_result = FormatterRegistry.format(tool_name, result)
            final_output_lines.append(formatted_result)
        else:
            final_output_lines.append(f"❌ Operation '{tool_name}' cancelled by user.")
            
    final_output = "\n\n".join(final_output_lines).strip()
    
    # [PHASE 4] Expert Opinion Pass (The Intelligence Layer)
    if is_insight_intent and final_output:
        try:
             from .agent_module import InsightAgent
             insight_agent = InsightAgent()
             # Truncate results if too large for the insight pass
             truncated_results = final_output[:4000] 
             prediction = insight_agent.forward(query=query, results_str=truncated_results)
             opinion = f"💡 **Expert Insight**:\n{prediction.expert_opinion}\n\n"
             final_output = opinion + final_output
        except Exception as e:
             # Fallback: Just return results if insight pass fails
             print(f"Expert Insight pass failed: {e}")

    # [OPTIMIZATION] Update Semantic Cache for future speed
    if not instant_tools and not cached_result and tool_calls and final_output:
        active_mcp = context_cache.get_last_mcp(session_id)
        await sem_cache.add(query, final_output, tool_calls, active_mcp=active_mcp)

    return {
        "output": final_output,
        "tool_calls": tool_calls
    }

async def _execute_batch_describe(
    result: Dict[str, Any],
    resource_type: str,
    prefix: str,
    full_detail: bool,
    namespace: str,
    log_callback=None
) -> Optional[Dict[str, Any]]:
    """
    Orchestrate parallel describe calls for batch describe feature.
    Extracts names from list result, generates parallel describe calls, aggregates results.
    """
    from .mcp.client import call_tool_async
    
    # Determine which key holds the resource list
    list_key_map = {
        "pod": "pods",
        "deployment": "deployments", 
        "service": "services",
        "node": "nodes"
    }
    list_key = list_key_map.get(resource_type, "pods")
    items = result.get(list_key, [])
    
    if not items:
        return None  # Nothing to describe
    
    # Build describe tool name
    describe_tool = f"{prefix}describe_{resource_type}"
    
    # Handle tool naming inconsistencies
    if resource_type == "service":
        describe_tool = f"{prefix}get_service"  # Services use 'get' not 'describe'
    
    if log_callback:
        log_callback("thought", f"🔄 Batch Describe: Describing {len(items)} {resource_type}s in parallel...")
    
    print(f"🚀 [BatchDescribe] Parallel execution: {len(items)} x {describe_tool}")
    
    # Build parallel tasks
    describe_tasks = []
    for item in items:
        name = item.get("name")
        if not name:
            continue
        
        args = {"namespace": namespace} if resource_type != "node" else {}
        
        # Set the name argument based on resource type
        if resource_type == "pod":
            args["pod_name"] = name
        elif resource_type == "node":
            args["node_name"] = name
        elif resource_type == "deployment":
            args["deployment_name"] = name
        elif resource_type == "service":
            args["service_name"] = name
        else:
            args["name"] = name
        
        describe_tasks.append(call_tool_async(describe_tool, args))
    
    # Execute all describes in parallel
    describe_results = await asyncio.gather(*describe_tasks, return_exceptions=True)
    
    # Aggregate results
    batch_output = []
    for i, (item, desc_result) in enumerate(zip(items, describe_results)):
        name = item.get("name", f"Resource {i+1}")
        status = item.get("phase", item.get("status", "Unknown"))
        
        if isinstance(desc_result, Exception):
            batch_output.append({
                "name": name,
                "status": status,
                "error": str(desc_result)
            })
        elif desc_result.get("success"):
            # Extract relevant details based on full_detail flag
            if full_detail:
                # Include full describe data
                batch_output.append({
                    "name": name,
                    "status": status,
                    "details": desc_result.get("data", desc_result)
                })
            else:
                # Compact summary - extract key info
                batch_output.append({
                    "name": name,
                    "status": status,
                    "events": _extract_events_summary(desc_result),
                    "conditions": _extract_conditions_summary(desc_result)
                })
        else:
            batch_output.append({
                "name": name,
                "status": status,
                "error": desc_result.get("error", "Unknown error")
            })
    
    return {
        "success": True,
        "_batch": True,
        "_full_detail": full_detail,
        "resource_type": resource_type,
        "resources": batch_output,
        "count": len(batch_output)
    }

def _extract_events_summary(result: Dict[str, Any]) -> str:
    """Extract brief events summary from describe result."""
    events = result.get("events", [])
    if not events:
        data = result.get("data", {})
        if isinstance(data, dict):
            events = data.get("events", [])
    
    if not events:
        return "No recent events"
    
    # Return last 2 events as summary
    recent = events[-2:] if len(events) > 2 else events
    return "; ".join([e.get("message", str(e))[:50] for e in recent])

def _extract_conditions_summary(result: Dict[str, Any]) -> str:
    """Extract brief conditions summary from describe result."""
    conditions = result.get("conditions", [])
    if not conditions:
        data = result.get("data", {})
        if isinstance(data, dict):
            conditions = data.get("conditions", [])
    
    if not conditions:
        return "No conditions"
    
    # Return failing conditions
    failing = [c for c in conditions if c.get("status") != "True"]
    if failing:
        return f"{len(failing)} issue(s): " + ", ".join([c.get("type", "Unknown") for c in failing[:3]])
    return "All conditions healthy"

def _extract_entities_from_result(tool_name: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to extract memorize-able entities from tool results."""
    entities = []
    
    # K8s Pods
    if "list_pods" in tool_name or "top_pods" in tool_name:
        for p in result.get("pods", []):
            entities.append({
                "name": p.get("name"), 
                "kind": "Pod",
                "ip": p.get("pod_ip") or p.get("ip"),
                "status": p.get("phase") or p.get("status"),
                "namespace": p.get("namespace", "default")
            })
            
    # K8s Nodes
    elif "list_nodes" in tool_name or "top_nodes" in tool_name:
         for n in result.get("nodes", []):
             entities.append({
                 "name": n.get("name"),
                 "kind": "Node",
                 "ip": n.get("internal_ip") or n.get("ip"),
                 "status": n.get("status")
             })
             
    # Docker Containers
    elif "list_containers" in tool_name:
        for c in result.get("containers", []):
            entities.append({
                "name": c.get("name"),
                "kind": "Container",
                "image": c.get("image"),
                "status": c.get("status"),
                "id": c.get("id")
            })
            
    return entities

async def execute_tool_calls_async(tool_calls: List[Dict]) -> Dict[str, Any]:
    """
    Execute a list of tool calls directly (used after disambiguation).
    """
    from .mcp.client import call_tool_async
    
    tasks = []
    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        arguments = tool_call.get("arguments", {})
        
        # [PHASE 6] Safety Check (Async Execution Flow)
        from .safety import analyze_risk
        risk = analyze_risk(tool_name, arguments)
        
        if risk.is_dangerous:
             # For disambiguation flow, we might need to break or return similar request
             # Since this is "execute_tool_calls", we should probably pause too.
             return {
                "output": f"⚠️ Action requires approval: {tool_name}",
                "tool_calls": tool_calls,
                "confirmation_request": {
                    "tool": tool_name,
                    "arguments": arguments,
                    "risk": risk.to_dict()
                }
            }
        else:
            print(f"[INFO] Scheduling tool {index + 1}/{len(tool_calls)}: {tool_name}")
            tasks.append((index, tool_name, call_tool_async(tool_name, arguments)))
    
    if not tasks:
        return {
            "output": "❌ All operations cancelled by user.",
            "tool_calls": tool_calls
        }
    
    # Execute
    coroutines = [t[2] for t in tasks]
    results = await asyncio.gather(*coroutines)
    
    # Format results
    execution_results = {}
    for i, res in enumerate(results):
        original_idx = tasks[i][0]
        tool_name = tasks[i][1]
        execution_results[original_idx] = (tool_name, res)
        
    final_output_lines = []
    
    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        
        if i in execution_results:
            _, result = execution_results[i]
            # 2. Add to context so agent can "see" what it did
            from .utils.compressor import ContextCompressor
            compressed_result = result
            if isinstance(result, str) and len(result) > 2000:
                 compressed_result = ContextCompressor.compress_k8s_describe(result, mode=compression_mode)
            elif isinstance(result, dict):
                 compressed_result = ContextCompressor.compress_json_result(result, mode=compression_mode)

            from .formatters import FormatterRegistry
            formatted = FormatterRegistry.format(tool_name, compressed_result)
            final_output_lines.append(formatted)
        else:
            final_output_lines.append(f"❌ Operation '{tool_name}' cancelled by user.")
            
    return {
        "output": "\n\n" + "-"*40 + "\n\n".join(final_output_lines),
        "tool_calls": tool_calls
    }

def process_query_with_error_handling(query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    try:
        return process_query(query, history)
    except KeyboardInterrupt:
        return {"output": "❌ Operation cancelled by user (Ctrl+C)", "tool_calls": []}
    except Exception as e:
        return {"output": f"❌ Unexpected error occurred: {str(e)}", "tool_calls": []}

def get_system_status(check_llm: bool = False) -> Dict[str, Any]:
    from .llm.ollama_client import MODEL
    
    llm_available = ensure_model_exists(force_test=check_llm)
    mcp_available = test_connection()
    k8s_mcp_available = test_k8s_connection()
    remote_k8s_available = test_remote_k8s_connection()
    
    docker_tools = [tool['name'] for tool in get_tools_schema()]
    k8s_tools = [tool['name'] for tool in get_k8s_tools_schema()]
    remote_k8s_tools = [tool['name'] for tool in get_remote_k8s_tools_schema()]
    
    return {
        "llm": {"available": llm_available, "model": MODEL},
        "docker_mcp_server": {"available": mcp_available, "url": "http://127.0.0.1:8080"},
        "k8s_mcp_server": {"available": k8s_mcp_available, "url": "http://127.0.0.1:8081"},
        "remote_k8s_mcp_server": {"available": remote_k8s_available, "url": "http://127.0.0.1:8082"},
        "tools": {
            "available": docker_tools + k8s_tools + remote_k8s_tools,
            "count": len(docker_tools + k8s_tools + remote_k8s_tools),
            "docker": docker_tools,
            "kubernetes": k8s_tools,
            "remote_kubernetes": remote_k8s_tools
        }
    }

def process_query_with_status_check(query: str, history: Optional[List[Dict[str, str]]] = None, check_llm: bool = False) -> Dict[str, Any]:
    status = get_system_status(check_llm=check_llm)
    if not status["llm"]["available"]:
        return {"output": f"❌ LLM not available.", "tool_calls": []}
    if not any([status["docker_mcp_server"]["available"], 
                status["k8s_mcp_server"]["available"], 
                status["remote_k8s_mcp_server"]["available"]]):
         return {"output": f"❌ No MCP servers available.", "tool_calls": []}
    return process_query_with_error_handling(query, history)