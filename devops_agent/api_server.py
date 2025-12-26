from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import json
import uuid
from datetime import datetime

# Import agent internals
from .agent import process_query_with_status_check, get_system_status
from .database.session_manager import session_manager
from .settings import settings
from .llm.ollama_client import list_available_models

DIRECT_CHAT_SYSTEM_PROMPT = """You are the DevOps Agent, a high-performance assistant for Docker and Kubernetes.
You are currently in a direct-chat mode. Keep your answers concise, technical, and accurate. 
Do not use large markdown blocks unless necessary for tables or logs.
If you need to perform actions (like listing pods), the user will usually trigger a tool-based mode.
If you recognize infrastructure names from the history, use them to provide high-fidelity context.
"""
import subprocess
import signal

# GLOBAL PROCESS STORE
# Map server_name -> Popen object
MCP_PROCESSES: Dict[str, subprocess.Popen] = {}

from contextlib import asynccontextmanager
from .pulse import get_pulse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    pulse = get_pulse()
    await pulse.start()
    yield
    # Shutdown
    await pulse.stop()
    from .mcp.client import close_async_client
    await close_async_client()

app = FastAPI(title="DevOps Agent API", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, align with "modern" reqs (Next.js usually 3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    model_override: Optional[str] = None
    mode: Optional[str] = "auto" # "auto", "chat", "agent"

class ConfigUpdateRequest(BaseModel):
    smart_model: Optional[str] = None
    fast_model: Optional[str] = None
    llm_host: Optional[str] = None
    fast_llm_host: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_host: Optional[str] = None

class SessionCreate(BaseModel):
    title: str

# --- Routes ---

@app.get("/health")
def health_check():
    return get_system_status(check_llm=False)

@app.get("/api/config")
def get_config():
    return {
        "models": {
            "smart": settings.LLM_MODEL,
            "fast": settings.LLM_FAST_MODEL or settings.LLM_MODEL,
            "embedding": settings.EMBEDDING_MODEL
        },
        "hosts": {
            "primary": settings.LLM_HOST,
            "fast": settings.LLM_FAST_HOST or settings.LLM_HOST,
            "embedding": settings.EMBEDDING_HOST
        },
        "available_models": list_available_models(settings.LLM_HOST)
    }

@app.post("/api/config")
async def update_config(data: ConfigUpdateRequest):
    # This is a runtime update. For persistence, we might need to write to .env
    # For now, we update the settings object in memory and try to update .env
    
    updates = []
    if data.smart_model:
        settings.LLM_MODEL = data.smart_model
        updates.append(f"DEVOPS_LLM_MODEL={data.smart_model}")
    if data.fast_model:
        settings.LLM_FAST_MODEL = data.fast_model
        updates.append(f"DEVOPS_LLM_FAST_MODEL={data.fast_model}")
    if data.llm_host:
        settings.LLM_HOST = data.llm_host
        updates.append(f"DEVOPS_LLM_HOST={data.llm_host}")
    if data.fast_llm_host:
        settings.LLM_FAST_HOST = data.fast_llm_host
        updates.append(f"DEVOPS_LLM_FAST_HOST={data.fast_llm_host}")
    if data.embedding_model:
        settings.EMBEDDING_MODEL = data.embedding_model
        updates.append(f"DEVOPS_EMBEDDING_MODEL={data.embedding_model}")
    if data.embedding_host:
        settings.EMBEDDING_HOST = data.embedding_host
        updates.append(f"DEVOPS_EMBEDDING_HOST={data.embedding_host}")
        
    # Simple .env appender for persistence (basic implementation)
    # Ideally reuse cli.py's logic or a proper env manager
    # We will just update the runtime settings for now as valid session config
    
    return {"status": "updated", "config": get_config()}

@app.get("/api/sessions")
def list_sessions():
    sessions = session_manager.list_sessions()
    # Convert to json-friendly list
    return [
        {
            "id": s.id,
            "title": s.title,
            "last_activity": s.last_activity,
            "message_count": len(s.messages)
        }
        for s in sessions
    ]

@app.post("/api/sessions")
def create_session(session: SessionCreate):
    new_session = session_manager.create_session(title=session.title)
    return {"id": new_session.id, "title": new_session.title}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "title": session.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "thoughts": m.thoughts if m.thoughts else None,
            }
            for m in session.messages
        ]
    }

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}

class ModelScanRequest(BaseModel):
    host: str

@app.post("/api/models/scan")
async def scan_models(request: ModelScanRequest):
    return {"models": list_available_models(request.host)}

class ModelPullRequest(BaseModel):
    model: str
    host: Optional[str] = None

@app.post("/api/models/pull")
async def pull_model_api(request: ModelPullRequest):
    from .llm.ollama_client import pull_model
    success = pull_model(request.model, host=request.host)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to pull model {request.model}")
    return {"status": "success", "model": request.model}

# =============================================
# RAG Index Management API
# =============================================

@app.get("/api/rag/status")
def rag_status():
    """Get FAISS index status and health."""
    try:
        from .rag.faiss_index import get_faiss_index
        faiss_idx = get_faiss_index()
        verification = faiss_idx.verify()
        return {
            "available": True,
            "tool_count": verification["tool_count"],
            "index_size": verification["index_size"],
            "healthy": verification["valid"],
            "issues": verification["issues"]
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "tool_count": 0,
            "healthy": False
        }

@app.get("/api/rag/list")
def rag_list():
    """List all indexed tools in FAISS."""
    try:
        from .rag.faiss_index import get_faiss_index
        faiss_idx = get_faiss_index()
        return {"tools": faiss_idx.list_all()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rag/rebuild")
async def rag_rebuild():
    """Rebuild the FAISS index from scratch."""
    try:
        from .rag.faiss_index import get_faiss_index
        from .tools import get_tools_schema
        from .k8s_tools import get_k8s_tools_schema
        from .llm.ollama_client import async_get_embeddings
        import asyncio
        
        faiss_idx = get_faiss_index()
        faiss_idx.clear()
        
        all_tools = get_tools_schema() + get_k8s_tools_schema()
        
        async def index_tool(tool):
            name = tool['name']
            text = f"{name}: {tool.get('description', '')}"
            emb = await async_get_embeddings(text)
            if emb:
                faiss_idx.add(name, emb, tool.get('description', ''))
                return True, name
            return False, name

        results = await asyncio.gather(*[index_tool(t) for t in all_tools])
        success = sum(1 for r in results if r[0])
        failed = [r[1] for r in results if not r[0]]
        
        return {
            "status": "rebuilt",
            "total": len(all_tools),
            "success": success,
            "failed": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/router/stats")
def router_stats():
    """Get Intent Router statistics."""
    try:
        from .router import get_router
        router = get_router()
        return {
            "template_count": len(router._templates),
            "semantic_example_count": len(router._semantic_intents),
            "auto_templates": len([t for t in router._templates if t.get("auto_generated")])
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/pulse/status")
def pulse_status():
    """Get real-time infrastructure status from the background pulse."""
    pulse = get_pulse()
    # Mask data for brief status
    status = {}
    for k, v in pulse.status_cache.items():
        if k == "global_index": continue
        status[k] = {
            "status": v.get("status"),
            "last_check": v.get("last_check")
        }
    return status

@app.get("/api/pulse/index")
def pulse_index():
    """Get the global infrastructure map (Resource Names -> Namespaces)."""
    pulse = get_pulse()
    index = pulse.status_cache.get("global_index", {}).get("resources", {})
    return {
        "index": index,
        "last_update": pulse.status_cache.get("global_index", {}).get("last_check")
    }

@app.get("/api/status")
def system_status():
    from .llm.ollama_client import check_model_access, check_embedding_access, list_available_models  # Import helpers
    
    # Base status
    s = get_system_status(check_llm=True)
    
    # Enrich with Fast/Smart specific checks
    start = datetime.now()
    
    smart_status = {
        "active": False, # Will be determined below
        "model": settings.LLM_MODEL,
        "host": settings.LLM_HOST
    }
    
    fast_status = {
        "active": False, # Will be determined below
        "model": settings.LLM_FAST_MODEL or settings.LLM_MODEL,
        "host": settings.LLM_FAST_HOST or settings.LLM_HOST
    }
    
    embedding_status = {
        "active": False, # Will be determined below
        "model": settings.EMBEDDING_MODEL,
        "host": settings.EMBEDDING_HOST
    }

    # Get available models for better matching
    def is_present(target, model_list):
        return any(m == target or m == f"{target}:latest" or m.startswith(f"{target}:") for m in model_list)

    smart_available = list_available_models(smart_status["host"])
    smart_status["active"] = is_present(smart_status["model"], smart_available)
    
    # Check Fast model 
    fast_available = smart_available
    if fast_status["host"] != smart_status["host"]:
        fast_available = list_available_models(fast_status["host"])
    fast_status["active"] = is_present(fast_status["model"], fast_available)

    # Check Embedding Model status
    embedding_available = list_available_models(embedding_status["host"])
    embedding_status["active"] = is_present(embedding_status["model"], embedding_available)
    
    # Final check: can we actually call them? (Deep health check)
    if smart_status["active"]:
        smart_status["active"] = check_model_access(smart_status["host"], smart_status["model"])
    if fast_status["active"]:
        if fast_status["host"] != smart_status["host"] or fast_status["model"] != smart_status["model"]:
            fast_status["active"] = check_model_access(fast_status["host"], fast_status["model"])
    if embedding_status["active"]:
        embedding_status["active"] = check_embedding_access(embedding_status["host"], embedding_status["model"])

    return {
        "agents": {
            "smart": smart_status,
            "fast": fast_status,
            "embedding": embedding_status
        },
        "mcp": {
            "docker": s["docker_mcp_server"]["available"],
            "k8s_local": s["k8s_mcp_server"]["available"],
            "k8s_remote": s["remote_k8s_mcp_server"]["available"]
        }
    }

class MCPStartRequest(BaseModel):
    servers: List[str] = ["docker", "k8s_local", "k8s_remote"] # Default to all if not specified

@app.post("/api/mcp/start")
async def start_mcp_servers(request: MCPStartRequest):
    import sys
    import os
    from .launcher import LOCK_FILE
    
    # Check if managed by Supervisor
    if os.path.exists(LOCK_FILE):
        return {
            "status": "managed", 
            "message": "Servers are managed by the Supervisor (launcher). Please use the CLI console to restart if needed, or stop the supervisor first.",
            "launched": [],
            "already_running": ["supervisor_mode"],
            "errors": []
        }

    base_cmd = [sys.executable, "-m", "devops_agent.cli"]
    cwd = os.getcwd()
    
    launched = []
    errors = []
    already_running = []

    try:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_CONSOLE

        def launch_server(name, cmd_args, port):
            if name in MCP_PROCESSES:
                # Check if actually alive
                if MCP_PROCESSES[name].poll() is None:
                    already_running.append(name)
                    return
                else:
                    # It died, cleanup
                    del MCP_PROCESSES[name]

            try:
                full_cmd = base_cmd + cmd_args
                print(f"DTOOL: Launching {name} on port {port}")
                p = subprocess.Popen(full_cmd, cwd=cwd, creationflags=flags)
                MCP_PROCESSES[name] = p
                launched.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")

        if "docker" in request.servers:
            launch_server("docker", ["server", "--port", str(settings.DOCKER_PORT)], settings.DOCKER_PORT)
        
        if "k8s_local" in request.servers:
             launch_server("k8s_local", ["k8s-server", "--port", str(settings.LOCAL_K8S_PORT)], settings.LOCAL_K8S_PORT)
        
        if "k8s_remote" in request.servers:
             launch_server("k8s_remote", ["remote-k8s-server", "--port", str(settings.REMOTE_K8S_PORT)], settings.REMOTE_K8S_PORT)
        
        return {
            "status": "completed", 
            "launched": launched, 
            "already_running": already_running,
            "errors": errors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MCPStopRequest(BaseModel):
    servers: List[str]

@app.post("/api/mcp/stop")
async def stop_mcp_servers(request: MCPStopRequest):
    stopped = []
    not_found = []
    errors = []

    for name in request.servers:
        if name in MCP_PROCESSES:
            p = MCP_PROCESSES[name]
            try:
                # Graceful terminate
                p.terminate()
                stopped.append(name)
                del MCP_PROCESSES[name]
            except Exception as e:
                errors.append(f"{name}: {e}")
        else:
            not_found.append(name)
            
    return {"status": "completed", "stopped": stopped, "not_found": not_found, "errors": errors}

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming endpoint for chat.
    Emits SSE events:
    - event: status (data: "Thinking...")
    - event: thought (data: "Looking for pods...")
    - event: output (data: "Found 3 pods...")
    - event: done (data: "[DONE]")
    """
    
    # Validation
    if not request.query:
        raise HTTPException(status_code=400, detail="Query required")

    session = None
    if request.session_id:
        session = session_manager.get_session(request.session_id)
    if not session:
        session = session_manager.create_session() # Ephemeral or new

    session_manager.set_active_session(session.id)

    # HISTORY construction
    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages[-10:] # Last 10 messages context
    ]

    async def _stream_direct_chat(query: str, history: List[Dict]):
        """Helper to stream direct LLM chat without Agent overhead."""
        # Dynamic Import
        from .llm.ollama_client import get_client
        client = get_client()
        
        yield f"event: status\ndata: Chatting with LLM (Direct)...\n\n"
        yield f"event: thought\ndata: ⚡ MODE: Optimized Chat (Bypassed Agent)\n\n"
        
        # Prepare messages including history and SYSTEM PROMPT
        messages = [{"role": "system", "content": DIRECT_CHAT_SYSTEM_PROMPT}] + history + [{"role": "user", "content": query}]
        
        stream = client.chat(
            model=settings.LLM_MODEL,
            messages=messages,
            stream=True
        )
        
        full_response = ""
        for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                full_response += content
                # Stream tokens
                payload = json.dumps({"token": content})
                yield f"event: token\ndata: {payload}\n\n"
                await asyncio.sleep(0.001)

        # Save to session (Fix: use session_manager instead of session.add_message)
        session_manager.add_message(session.id, "user", query)
        session_manager.add_message(session.id, "assistant", full_response)
        
        yield f"event: done\ndata: [DONE]\n\n"

    async def event_generator():
        # 1. Acknowledge
        yield f"event: status\ndata: Analyzing request...\n\n"
        await asyncio.sleep(0.1)

        # DETERMINING MODE
        target_mcps = []
        is_direct_chat = False

        if request.mode == "chat":
            is_direct_chat = True
        elif request.mode == "auto":
            from .smart_router import smart_router
            target_mcps = smart_router.route(request.query, session_id=session.id)
            
            # OPTIMIZATION: If ONLY chat is selected, use direct chat!
            if len(target_mcps) == 1 and target_mcps[0] == "chat":
                 is_direct_chat = True
            elif not target_mcps:
                 # Fallback if router fails?
                 target_mcps = ["docker", "k8s_local", "k8s_remote"]
        
        # EXECUTION
        if is_direct_chat:
             async for event in _stream_direct_chat(request.query, history):
                 yield event
             return

        # --- AGENT MODE streaming via Queue ---
        # Create a queue to bridge the sync/async callbacks to our generator
        queue = asyncio.Queue()
        
        def monitor_callback(event_type: str, message: str):
            # This runs in the agent's loop. We need to put it into the asyncio queue
            # Since process_query_async is async, we can just use put_nowait if loop is same?
            # Yes, api_server runs on main loop.
            try:
                queue.put_nowait((event_type, message))
            except Exception as e:
                print(f"Queue Error: {e}")

        # Task to run agent
        async def run_agent():
            try:
                from .agent import process_query_async
                
                # Determine forced mode if any
                forced = None
                
                # If we detected MCPs via "auto" smart router, pass them as forced?
                # Actually, agent.py calls smart router internally if forced is None.
                # BUT, to save time (since we already called it), we can pass it!
                # Wait, agent.py 'forced_mcps' bypasses the router logic inside agent?
                # Yes. So passing target_mcps here optimizes agent startup too!
                if request.mode == "auto" and target_mcps:
                    forced = target_mcps
                
                # Explicit overrides
                if request.mode == "docker": forced = ["docker"]
                elif request.mode == "k8s_local": forced = ["k8s_local"]
                elif request.mode == "k8s_remote": forced = ["k8s_remote"]
                
                # We yield a "thinking" status first
                queue.put_nowait(("status", "Thinking (Agent Active)..."))
                
                if forced:
                     queue.put_nowait(("thought", f"ROUTER: Specialized Agents -> {forced}"))
                
                result = await process_query_async(request.query, history=history, log_callback=monitor_callback, session_id=session.id, forced_mcps=forced)
                
                queue.put_nowait(("result", result))
            except Exception as e:
                queue.put_nowait(("error", str(e)))
        
        # Start background task
        task = asyncio.create_task(run_agent())
        
        # Thoughts collection for persistence
        collected_thoughts = []
        
        while True:
            # Wait for next event or task completion
            # We use wait_for to allow checking task status
            try:
                # Wait for an item
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                
                msg_type, msg_data = item
                
                if msg_type == "result":
                    # Final result processing
                    result = msg_data
                    
                    # Send Tool Calls info explicitly if not logged yet
                    if result.get("tool_calls"):
                        tools_used = [t["name"] for t in result["tool_calls"]]
                        thought_content = f"🛠️ Tools Selected: {', '.join(tools_used)}"
                        collected_thoughts.append({"type": "tool_call", "content": thought_content})
                        yield f"event: thought\ndata: {thought_content}\n\n"
                        yield f"event: tool_calls\ndata: {json.dumps(result['tool_calls'])}\n\n"
                        
                    # Check for disambiguation
                    if result.get("disambiguation_needed"):
                         yield f"event: error\ndata: Disambiguation needed (Not implemented in stream yet)\n\n"
                    
                    # Stream Output
                    output_text = result.get("output", "")
                    
                    chunk_size = 50
                    for i in range(0, len(output_text), chunk_size):
                        chunk = output_text[i:i+chunk_size]
                        payload = json.dumps({"token": chunk})
                        yield f"event: token\ndata: {payload}\n\n"
                        await asyncio.sleep(0.01)

                    # Save to session with thoughts
                    session_manager.add_message(session.id, "user", request.query)
                    assistant_msg_id = session_manager.add_message(session.id, "assistant", output_text)
                    
                    # Save collected thoughts (linked to assistant message)
                    if collected_thoughts and assistant_msg_id:
                        session_manager.add_thoughts(assistant_msg_id, collected_thoughts)

                    # Handle Confirmation Request
                    if result.get("confirmation_request"):
                        # Send specific event for UI to render the card
                        # Enrich with risk assessment details for the frontend
                        payload_data = result["confirmation_request"]
                        if result.get("risk"):
                             payload_data["risk"] = result["risk"]
                        
                        payload = json.dumps(payload_data)
                        yield f"event: confirmation_request\ndata: {payload}\n\n"
                        yield f"event: done\ndata: [DONE]\n\n"
                        break
                    
                    yield f"event: done\ndata: [DONE]\n\n"
                    break
                    
                elif msg_type == "error":
                    yield f"event: error\ndata: {msg_data}\n\n"
                    break
                    
                else:
                    # Generic event (thought, status) - collect for persistence
                    safe_data = msg_data.replace("\n", " ")
                    collected_thoughts.append({"type": msg_type, "content": safe_data})
                    yield f"event: {msg_type}\ndata: {safe_data}\n\n"
                    
            except asyncio.TimeoutError:
                if task.done():
                    # If task is done but we are here, maybe it didn't put result? 
                    # Or exception wasn't caught?
                    # Check exception
                    if task.exception():
                        yield f"event: error\ndata: Internal Agent Error: {task.exception()}\n\n"
                    break
                continue # Keep waiting

    return StreamingResponse(event_generator(), media_type="text/event-stream")

class ConfirmRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    session_id: Optional[str] = None

@app.post("/api/chat/confirm")
async def confirm_action_api(request: ConfirmRequest):
    """
    Execute a tool that was previously paused for confirmation.
    """
    from .mcp.client import call_tool_async
    from .agent import format_tool_result
    
    # 1. Execute
    try:
        result = await call_tool_async(request.tool, request.arguments)
        from .formatters import FormatterRegistry
        formatted = FormatterRegistry.format(request.tool, result)
        
        # 2. Append to session history (if session_id provided)
        if request.session_id:
            session = session_manager.get_session(request.session_id)
            if session:
                # We log this as a "System/Agent" continuation
                # User: [Implicitly Confirmed]
                session.add_message("user", f"Verified action: {request.tool}")
                session.add_message("assistant", formatted)

        return {"output": formatted, "result": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
