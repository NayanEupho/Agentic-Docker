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
from .safety import confirm_action_auto
from .tools import get_tools_schema
from .k8s_tools import get_k8s_tools_schema
from .k8s_tools.remote_k8s_tools import get_remote_k8s_tools_schema
from typing import Dict, Any, List, Optional
import asyncio

def process_query(query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Process a user's natural language query and return result with metadata.
    Returns: {"output": str, "tool_calls": List[dict]}
    """
    return asyncio.run(process_query_async(query, history))

async def process_query_async(query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Async implementation of query processing with parallel tool execution.
    Returns: {"output": str, "tool_calls": List[dict]}
    """
    # 1. Get all available tools schemas
    docker_tools_schema = get_tools_schema()
    k8s_tools_schema = get_k8s_tools_schema()
    remote_k8s_tools_schema = get_remote_k8s_tools_schema()
    
    # Combine all schemas for the LLM
    all_tools_schema = docker_tools_schema + k8s_tools_schema + remote_k8s_tools_schema
    
    # 2. Ask DSPy Agent to choose tool(s)
    # Lazy initialization of DSPy (if not already done)
    # In a production app, we might do this at startup.
    # 2. Ask DSPy Agent to choose tool(s)
    # Lazy initialization of DSPy (if not already done)
    # In a production app, we might do this at startup.
    from .dspy_client import init_dspy_lms
    from .agent_module import DockerAgent, parse_dspy_tool_calls
    
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

    # Instantiate the agent (ReAct / CoT) with dual models
    agent = DockerAgent(fast_lm=fast_lm, smart_lm=smart_lm)
    import time
    t_start = time.time()
    
    # --- RICH CONTEXT: STATE INJECTION ---
    # Fetch live state to help the agent verify resource names
    context_str = ""
    try:
        t_ctx_start = time.time()
        # Run detailed discovery in parallel
        # Run detailed discovery in parallel
        # We use the actual tools to get the source-of-truth
        ctx_tasks = [
            call_tool_async("docker_list_containers", {"all": False}),
            call_tool_async("local_k8s_list_pods", {"namespace": "default"}),
            call_tool_async("remote_k8s_list_nodes", {}),  # Get Remote Nodes (for names like kc-m1)
        ]
        
        # TIMEOUT: We give context fetching max 1.5s. If it's slower, we skip it to keep chat snappy.
        ctx_results = await asyncio.wait_for(asyncio.gather(*ctx_tasks, return_exceptions=True), timeout=1.5)
        
        # Parse Containers
        containers = []
        if isinstance(ctx_results[0], dict) and ctx_results[0].get("success"):
            containers = [c["name"] for c in ctx_results[0].get("containers", [])]
            
        # Parse Pods
        pods = []
        if isinstance(ctx_results[1], dict) and ctx_results[1].get("success"):
            pods = [p["name"] for p in ctx_results[1].get("pods", [])]
            
        # Parse Remote Nodes
        nodes = []
        if len(ctx_results) > 2 and isinstance(ctx_results[2], dict) and ctx_results[2].get("success"):
            nodes = [n["name"] for n in ctx_results[2].get("nodes", [])]
            
        context_parts = []
        if containers:
            context_parts.append(f"Running Containers: {', '.join(containers)}")
        if pods:
            context_parts.append(f"Active Pods (Default): {', '.join(pods)}")
        if nodes:
            context_parts.append(f"Available Nodes (Remote): {', '.join(nodes)}")
            
        if context_parts:
            context_str = "\n[System Context: " + " | ".join(context_parts) + "]"
            print(f"🔎 Injected Context: {context_str}")
        
        print(f"⏱️ [PERF] Context Injection: {time.time() - t_ctx_start:.2f}s")
            
    except Exception as e:
        print(f"⚠️  Context injection failed (skipping): {e}")

    # Inject context into query
    full_query = query + context_str if context_str else query

    print(f"🧠 DSPy Agent Thinking... (Query: {full_query})")
    try:
        t_agent_start = time.time()
        prediction = agent(query=query, tools_schema=all_tools_schema, history=history)
        print(f"⏱️ [PERF] Agent Inference: {time.time() - t_agent_start:.2f}s")
        
        # Extract the tool_calls from the prediction
        # dspy.ChainOfThought puts the reasoning in `prediction.reasoning`
        # and the output field in `prediction.tool_calls`
        raw_tool_calls = prediction.tool_calls
        print(f"🐛 DSPy Raw Output: {raw_tool_calls}")
        
        tool_calls = parse_dspy_tool_calls(raw_tool_calls)
        
    except Exception as e:
        print(f"❌ DSPy Execution Error: {e}")
        return {
            "output": f"❌ Brain freeze! The agent encountered an error: {e}",
            "tool_calls": []
        }
    
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
        "k8s_list_pods": "remote_k8s_list_pods",
        "k8s_list_nodes": "remote_k8s_list_nodes",
        "k8s_list_deployments": "remote_k8s_list_deployments",
        "k8s_describe_node": "remote_k8s_describe_node",
        "k8s_describe_deployment": "remote_k8s_describe_deployment",
        
        # Remote -> Local
        "remote_k8s_list_pods": "k8s_list_pods",
        "remote_k8s_list_nodes": "k8s_list_nodes",
        "remote_k8s_list_deployments": "k8s_list_deployments",
        "remote_k8s_describe_node": "k8s_describe_node",
        "remote_k8s_describe_deployment": "k8s_describe_deployment",
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
                if "local_k8s_" in content or '"k8s_' in content: # local tools
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
                
            # CASE 5: Mixed or No Context -> PROMPT USER
            return {
                "output": "",
                "tool_calls": tool_calls,
                "disambiguation_needed": True,
                "ambiguous_tool": tool_name,
                "options": {
                    "1": {"label": "Local Kubernetes", "tool": local_tool},
                    "2": {"label": "Remote Kubernetes", "tool": remote_tool}
                }
            }
    
    # 3. Plan execution
    tasks = []
    
    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]
        
        # Safety Check
        if not confirm_action_auto(tool_name, arguments):
            pass
        else:
            print(f"[INFO] Scheduling tool {index + 1}/{len(tool_calls)}: {tool_name}")
            tasks.append((index, tool_name, call_tool_async(tool_name, arguments)))
    
    if not tasks:
        if tool_calls and len(tasks) == 0:
            return {
                "output": "❌ All operations cancelled by user.",
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
            formatted_result = format_tool_result(tool_name, result)
            final_output_lines.append(formatted_result)
        else:
            final_output_lines.append(f"❌ Operation '{tool_name}' cancelled by user.")
            
    return {
        "output": "\n\n" + "-"*40 + "\n\n".join(final_output_lines),
        "tool_calls": tool_calls
    }

async def execute_tool_calls_async(tool_calls: List[Dict]) -> Dict[str, Any]:
    """
    Execute a list of tool calls directly (used after disambiguation).
    """
    from .mcp.client import call_tool_async
    
    tasks = []
    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        arguments = tool_call.get("arguments", {})
        
        # Safety Check
        if not confirm_action_auto(tool_name, arguments):
            pass
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
            formatted_result = format_tool_result(tool_name, result)
            final_output_lines.append(formatted_result)
        else:
            final_output_lines.append(f"❌ Operation '{tool_name}' cancelled by user.")
            
    return {
        "output": "\n\n" + "-"*40 + "\n\n".join(final_output_lines),
        "tool_calls": tool_calls
    }

def format_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """Helper function to format results."""
    
    # 1. Handle AI Error Interpretation (High Priority)
    # 1. Handle AI Error Interpretation (High Priority)
    if result.get("raw_error"):
        from .agent_module import ErrorAnalyzer
        
        analyzer = ErrorAnalyzer()
        prediction = analyzer(
            user_query="User ran " + tool_name,
            error_summary=result.get("error", "Unknown error"),
            raw_error=result.get("raw_error")
        )
        return f"❌ Operation failed: {result.get('error')}\n\n🤖 **AI Explanation:**\n{prediction.explanation}"

    # 2. Handle Success Cases
    if result.get("success"):
        if tool_name == "docker_list_containers":
            containers = result.get("containers", [])
            count = result.get("count", 0)
            if not containers: return "✅ Success! No containers found."
            lines = [f"✅ Success! Found {count} container(s):"]
            for c in containers:
                status_emoji = "🟢" if "Up" in c.get('status', '') else "🔴"
                lines.append(f"   {status_emoji} {c['name']} ({c['id'][:12]}) - {c['image']} [{c['status']}]")
            return "\n".join(lines)
            
        elif tool_name == "docker_run_container":
             msg = result.get("message", "Container started.")
             return f"✅ {msg}\n   Container ID: {result.get('container_id')}\n   Name: {result.get('name')}"

        elif tool_name == "docker_stop_container":
             msg = result.get("message", "Container stopped.")
             return f"✅ {msg}\n   Container ID: {result.get('container_id')}\n   Name: {result.get('name')}"

        elif "list_pods" in tool_name:
             pods = result.get("pods", [])
             ns = result.get("namespace", "unknown")
             scope = "REMOTE" if "remote" in tool_name else "LOCAL"
             if not pods: return f"✅ Success! No pods in '{ns}' ({scope})."
             lines = [f"✅ Success! Found {len(pods)} pod(s) in '{ns}' ({scope}):"]
             for p in pods:
                 phase = p.get('phase', 'Unknown')
                 emoji = "🟢" if phase == "Running" else "🔴"
                 lines.append(f"   {emoji} {p['name']} ({p.get('pod_ip', 'N/A')}) - {phase}")
             return "\n".join(lines)
        
        elif "list_nodes" in tool_name:
             nodes = result.get("nodes", [])
             scope = "REMOTE" if "remote" in tool_name else "LOCAL"
             if not nodes: return f"✅ Success! No nodes found ({scope})."
             lines = [f"✅ Success! Found {len(nodes)} node(s) ({scope}):"]
             for n in nodes:
                 status = n.get('status', 'Unknown')
                 emoji = "🟢" if status == "Ready" else "🔴"
                 ip_str = f" ({n.get('internal_ip', 'N/A')})" if n.get('internal_ip') else ""
                 lines.append(f"   {emoji} {n['name']}{ip_str} - {status}")
             return "\n".join(lines)
        
        elif tool_name == "remote_k8s_list_namespaces":
            namespaces = result.get("namespaces", [])
            if not namespaces: return "✅ Success! No namespaces found."
            lines = [f"✅ Success! Found {len(namespaces)} namespaces:"]
            for ns in namespaces:
                status = ns.get('status', 'Active')
                emoji = "🟢" if status == "Active" else "🔴"
                lines.append(f"   {emoji} {ns['name']} - {status}")
            return "\n".join(lines)
            
        elif tool_name == "remote_k8s_describe_node":
            node = result.get("node", {})
            if not node: return "✅ Success! Node found but no details returned."
            
            lines = [f"✅ Node: {node.get('name')}"]
            # Add general info
            sys = node.get('system_info', {})
            lines.append(f"   OS: {sys.get('os_image')} ({sys.get('architecture')}) | Kernel: {sys.get('kernel_version')}")
             
            # Addresses
            addrs = node.get('addresses', {})
            if isinstance(addrs, dict):
                addr_str = ", ".join([f"{k}: {v}" for k, v in addrs.items()])
            else:
                addr_str = str(addrs)
            lines.append(f"   Addresses: {addr_str}")
            
            # Conditions
            lines.append("   Conditions:")
            for cond in node.get('conditions', []):
                status_icon = "🟢"
                if cond.get('type') == 'Ready':
                    status_icon = "🟢" if cond.get('status') == 'True' else "🔴"
                elif cond.get('status') == 'True': # Bad things like DiskPressure
                    status_icon = "🔴"
                     
                lines.append(f"     {status_icon} {cond.get('type')}: {cond.get('status')} ")
                if cond.get('message'):
                     lines.append(f"       Pop: {cond.get('message')}")

            # Capacity
            alloc = node.get('allocatable', {})
            lines.append(f"   Resources: CPU: {alloc.get('cpu')} | Mem: {alloc.get('memory')} | Pods: {alloc.get('pods')}")
            
            return "\n".join(lines)
            
        elif tool_name == "remote_k8s_list_services":
            services = result.get("services", [])
            scope = result.get("scope", "unknown scope")
            if not services: return f"✅ Success! No services found in {scope}."
            
            lines = [f"✅ Success! Found {len(services)} services in {scope}:"]
            for svc in services:
                name = svc.get('name')
                svc_type = svc.get('type')
                cluster_ip = svc.get('cluster_ip')
                ext_ips = svc.get('external_ips')
                ext_ip_str = ",".join(ext_ips) if ext_ips else "<none>"
                ports = ", ".join(svc.get('ports', []))
                
                lines.append(f"   🔹 {name} ({svc_type}) | IP: {cluster_ip} | Ext: {ext_ip_str} | Ports: {ports}")
            return "\n".join(lines)

        elif tool_name == "remote_k8s_get_service":
            svc = result.get("service", {})
            if not svc: return "✅ Success! Service found but no details returned."
            
            lines = [f"✅ Service: {svc.get('name')}"]
            lines.append(f"   Namespace: {svc.get('namespace')}")
            lines.append(f"   Type: {svc.get('type')}")
            lines.append(f"   Cluster IP: {svc.get('cluster_ip')}")
            
            # External IPs
            ext_ips = svc.get('external_ips')
            if ext_ips:
                lines.append(f"   External IPs: {', '.join(ext_ips)}")
            
            # Load Balancer
            lb = svc.get('load_balancer_ip', [])
            if lb:
                lb_ips = [i.get('ip', 'unknown') for i in lb]
                lines.append(f"   LoadBalancer Ingress: {', '.join(lb_ips)}")

            # Ports
            lines.append("   Ports:")
            for p in svc.get('ports', []):
                lines.append(f"     - {p.get('name', 'unnamed')}: {p.get('port')}/{p.get('protocol')} -> {p.get('targetPort')}")
            
            # Selector
            selector = svc.get('selector')
            if selector:
               selector_str = ", ".join([f"{k}={v}" for k,v in selector.items()])
               lines.append(f"   Selector: {selector_str}")
               
            return "\n".join(lines)

        elif tool_name == "remote_k8s_get_resources_ips":
            ips = result.get("ips", {})
            lines = [f"✅ Success! Found IPs for {len(ips)} resource(s):"]
            for name, info in ips.items():
                if isinstance(info, dict):
                    # Pod info
                    if "pod_ip" in info:
                        lines.append(f"   🔹 {name}: IP={info.get('pod_ip')} (Host={info.get('host_ip')})")
                    # Node info
                    else:
                        addr_str = ", ".join([f"{k}={v}" for k,v in info.items()])
                        lines.append(f"   🔹 {name}: {addr_str}")
                else:
                    lines.append(f"   🔸 {name}: {info}")
            return "\n".join(lines)

        elif tool_name == "remote_k8s_describe_pod":
            pod = result.get("pod", {})
            if not pod: return "✅ Success! Pod found but no details returned."
            
            lines = [f"✅ Pod: {pod.get('name')}"]
            lines.append(f"   Namespace: {pod.get('namespace')}")
            lines.append(f"   Node: {pod.get('node_name')} | IP: {pod.get('pod_ip')} | Phase: {pod.get('phase')}")
            lines.append(f"   Start Time: {pod.get('start_time')}")
            
            # Containers
            lines.append("   Containers:")
            for c in pod.get('containers', []):
                ready_icon = "🟢" if c.get('ready') else "🔴"
                state = c.get('state', {})
                state_str = "Unknown"
                if state:
                    state_str = list(state.keys())[0] # e.g. running, waiting
                
                lines.append(f"     {ready_icon} {c.get('name')} ({c.get('image')})")
                lines.append(f"       State: {state_str} | Restarts: {c.get('restart_count')}")
            
            # Conditions
            lines.append("   Conditions:")
            for cond in pod.get('conditions', []):
                status_icon = "🟢" if cond.get('status') == 'True' else "🔴"
                lines.append(f"     {status_icon} {cond.get('type')}")

            # Events
            events = pod.get('events', [])
            if events:
                 lines.append("   Events (Recent):")
                 for e in events[-5:]: # Last 5 events
                     icon = "⚠️" if e.get('type') == 'Warning' else "ℹ️"
                     lines.append(f"     {icon} {e.get('reason')}: {e.get('message')} (x{e.get('count')})")
            else:
                 lines.append("   Events: <none>")

            return "\n".join(lines)

        elif tool_name == "remote_k8s_describe_namespace":
            ns = result.get("namespace", {})
            if not ns: return "✅ Success! Namespace found but no details."
            
            lines = [f"✅ Namespace: {ns.get('name')}"]
            lines.append(f"   Status: {ns.get('status')}")
            lines.append(f"   Created: {ns.get('creation_timestamp')}")
            
            labels = ns.get('labels', {})
            if labels:
                lines.append("   Labels:")
                for k, v in labels.items():
                    lines.append(f"     {k}={v}")
                
            return "\n".join(lines)

        elif tool_name == "remote_k8s_describe_service":
             svc = result.get("service", {})
             if not svc: return "✅ Success! Service found but no details returned."
             
             lines = [f"✅ Service: {svc.get('name')}"]
             lines.append(f"   Namespace: {svc.get('namespace')}")
             lines.append(f"   Type: {svc.get('type')}")
             lines.append(f"   Cluster IP: {svc.get('cluster_ip')}")
             
             eps = svc.get('endpoints', [])
             if eps:
                 lines.append(f"   Endpoints: {', '.join(eps)}")
             else:
                 lines.append("   Endpoints: <none>")
                 
             events = svc.get('events', [])
             if events:
                  lines.append("   Events (Recent):")
                  for e in events[-5:]:
                      icon = "⚠️" if e.get('type') == 'Warning' else "ℹ️"
                      lines.append(f"     {icon} {e.get('reason')}: {e.get('message')} (x{e.get('count')})")
             
             return "\n".join(lines)


        
        elif tool_name == "chat":
             return f"🗣️ {result.get('message', '')}"

        else:
            return f"✅ Success! {result.get('message', 'Operation completed.')}"
    else:
        return f"❌ Operation failed: {result.get('error', 'Unknown error')}"

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