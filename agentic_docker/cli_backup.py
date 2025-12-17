# agentic_docker/cli.py
"""
Command-Line Interface (CLI)

This module defines the command-line interface for the Agentic Docker tool.
It uses Typer to create user-friendly commands and handles argument parsing,
help text, and command execution. This is the main entry point for users.
"""

# Import Typer - a modern library for building CLI applications
import typer
# Import typing utilities for type hints
from typing import Optional
# Import our agent that processes queries
from .agent import process_query_with_status_check
# Import the MCP server function
from .mcp.server import start_mcp_server
# Import the K8s MCP server function
from .mcp.local_k8s_server import start_k8s_mcp_server
# Import system status function
from .agent import get_system_status

# Create the main Typer application instance
app = typer.Typer(
    name="agentic-docker",
    help="An AI-powered Docker assistant that understands natural language commands.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich"
)

# Create a sub-command group for session management
session_app = typer.Typer(
    name="session",
    help="Manage conversation sessions and context."
)
app.add_typer(session_app, name="session")

@session_app.command("start")
def start_session(
    title: str = typer.Argument(..., help="Title for the new session")
):
    """
    Start a new named session and set it as active.
    All subsequent 'run' commands will use this session context.
    """
    from .database.session_manager import session_manager
    session = session_manager.create_session(title=title)
    session_manager.set_active_session(session.id)
    typer.echo(f"✅ Session started: {title} (ID: {session.id})")
    typer.echo("   All subsequent commands will automatically use this session.")
    typer.echo("   Run 'agentic-docker session end' to stop.")

@session_app.command("end")
def end_session():
    """
    End the current active session.
    """
    from .database.session_manager import session_manager
    active_id = session_manager.get_active_session_id()
    if active_id:
        session_manager.clear_active_session()
        typer.echo(f"🛑 Session ended (ID: {active_id})")
    else:
        typer.echo("⚠️  No active session found.")

@session_app.command("list")
def list_sessions():
    """
    List all conversation sessions.
    """
    from .database.session_manager import session_manager
    sessions = session_manager.list_sessions()
    
    if not sessions:
        typer.echo("📜 No conversation history found.")
        return

    # Check for active session to highlight it
    active_id = session_manager.get_active_session_id()

    typer.echo(f"📜 Found {len(sessions)} sessions:")
    for session in sessions:
        msg_count = len(session.messages)
        title = session.title if session.title else f"Session {session.id}"
        
        # Add visual indicator for active session
        prefix = "✅" if session.id == active_id else "•"
        
        last_activity = session.last_activity
            
        typer.echo(f"   {prefix} {title} (ID: {session.id})")
        typer.echo(f"     Last Active: {last_activity} | Messages: {msg_count}")
        typer.echo("")

@session_app.command("show")
def show_session(session_id: str):
    """
    Show logs for a specific session.
    """
    from .database.session_manager import session_manager
    session = session_manager.get_session(session_id)
    
    if not session:
        typer.echo(f"❌ Session {session_id} not found.")
        return
        
    title = session.title if session.title else f"Session {session.id}"
    typer.echo(f"📜 {title} (ID: {session.id})")
    typer.echo("-" * 50)
    for msg in session.messages:
        role_icon = "👤" if msg.role == "user" else "🤖"
        typer.echo(f"{role_icon} [{msg.timestamp}] {msg.role.upper()}:")
        typer.echo(f"   {msg.content}")
        typer.echo("")

@session_app.command("clear")
def clear_sessions(
    session_id: Optional[str] = typer.Argument(None, help="Specific session ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
):
    """
    Clear conversation history.
    """
    from .database.session_manager import session_manager
    
    if session_id:
        if not force:
            if not typer.confirm(f"Are you sure you want to delete session {session_id}?"):
                return
        if session_manager.delete_session(session_id):
            typer.echo(f"✅ Session {session_id} deleted.")
        else:
            typer.echo(f"❌ Session {session_id} not found.")
    else:
        if not force:
            if not typer.confirm("Are you sure you want to DELETE ALL history?"):
                return
        session_manager.clear_all()
        typer.echo("✅ All history deleted.")


@app.command(
    name="run",
    help="Execute a Docker command in natural language."
)
def run_command(
    query: str = typer.Argument(
        ...,
        help="Your natural language Docker command (e.g., 'Start nginx on port 8080')"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed processing information"
    ),
    no_confirm: bool = typer.Option(
        False,
        "--no-confirm",
        "-y",
        help="Skip safety confirmation prompts (use with caution!)"
    ),
    session_id: Optional[str] = typer.Option(
        None,
        "--session",
        "-s",
        help="Resume a specific conversation session ID"
    ),
    check_llm: bool = typer.Option(
        False,
        "--check-llm",
        help="Perform an explicit test of the LLM connection before running (slower)"
    )
):
    """
    Execute a Docker command using natural language.
    """
    # Import safety module to potentially modify confirmation behavior
    from .safety import USE_DETAILED_CONFIRMATION
    
    # Handle the --no-confirm flag
    if no_confirm:
        # Temporarily disable detailed confirmation for this run
        import agentic_docker.safety as safety_module
        original_detailed = safety_module.USE_DETAILED_CONFIRMATION
        safety_module.USE_DETAILED_CONFIRMATION = False
        print("⚠️  Safety confirmation disabled with --no-confirm flag")
    
    if verbose:
        print(f"🔍 Processing query: '{query}'")
        print("📊 System status check...")
        status = get_system_status()
        print(f"   LLM: {'✅ Available' if status['llm']['available'] else '❌ Unavailable'}")
        print(f"   MCP Server: {'✅ Available' if status['docker_mcp_server']['available'] else '❌ Unavailable'}")
        print(f"   Tools: {len(status['tools']['available'])} available")
        print("-" * 50)
    
    try:
        # Session Management
        from .database.session_manager import session_manager
        
        current_session = None
        if session_id:
             # Explicit flag specified: use it (find or create)
            current_session = session_manager.get_session(session_id)
            if not current_session:
                typer.echo(f"⚠️  Session {session_id} not found. Creating a new one.")
                current_session = session_manager.create_session(session_id=session_id)
        else:
            # Check for global active session
            active_id = session_manager.get_active_session_id()
            if active_id:
                current_session = session_manager.get_session(active_id)
                if not current_session:
                     # Active session ID points to non-existent session (was deleted?)
                     session_manager.clear_active_session()
                     current_session = session_manager.create_session()
                else:
                    title = current_session.title if current_session.title else current_session.id
                    typer.echo(f"🔄 Using active session: {title}")
            else:
                # No active session, create ephemeral
                current_session = session_manager.create_session()
            
        # VISUAL CONTEXT INDICATOR
        from .settings import settings
        host_label = "Remote" if "localhost" not in settings.LLM_HOST and "127.0.0.1" not in settings.LLM_HOST else "Local"
        typer.echo(f"🤖 Context: [{host_label} | {settings.LLM_MODEL}]")
        typer.echo(f"🛑 Session ID: {current_session.id}")
        
        # Log user query
        session_manager.add_message(current_session.id, "user", query)
        
        # Prepare history for the agent
        # CRITICAL FIX: Truncate large outputs to prevent LLM hallucination/stickiness
        history = []
        for msg in current_session.messages:
            if msg.role == "system":
                continue
            
            content = msg.content
            # If it's a generic system output, truncate it heavily
            if "[System Output]" in content and len(content) > 500:
                content = content[:500] + "... (truncated)"
            
            history.append({"role": msg.role, "content": content})
        
        # Process the query through our agent with history
        result_pkg = process_query_with_status_check(query, history, check_llm=check_llm)
        
        # --- DISAMBIGUATION HANDLING ---
        if result_pkg.get("disambiguation_needed"):
            options = result_pkg.get("options", {})
            typer.echo("\n🤔 This query is ambiguous. Please select the target:")
            for key, opt in options.items():
                typer.echo(f"   [{key}] {opt['label']}")
            
            choice = typer.prompt("Enter your choice", default="1")
            
            if choice in options:
                # Update the tool call with the selected tool
                selected_tool = options[choice]["tool"]
                tool_calls = result_pkg.get("tool_calls", [])
                for tc in tool_calls:
                    if tc["name"] == result_pkg.get("ambiguous_tool"):
                        tc["name"] = selected_tool
                
                # Re-run with the corrected tool (directly execute)
                from .agent import execute_tool_calls_async
                import asyncio
                result_pkg = asyncio.run(execute_tool_calls_async(tool_calls))
            else:
                typer.echo("❌ Invalid choice. Aborting.")
                raise typer.Exit(code=1)
        
        # 1. Log Assistant Tool Calls (The "Thought")
        # This restores the User -> Assistant -> User flow.
        import json
        tool_calls = result_pkg.get("tool_calls", [])
        if tool_calls:
            # We dump the tool calls as JSON, which is what the LLM ostensibly generated
            session_manager.add_message(current_session.id, "assistant", json.dumps(tool_calls))
        
        # 2. Log System Output (The "Observation")
        # Log agent response - CLEAN IT FIRST and save as SYSTEM OUTPUT (not assistant)
        clean_result = result_pkg.get("output", "")
        if "----------------------------------------" in clean_result:
             # Strip the separator line and everything before it if it looks like a prefix
             parts = clean_result.split("----------------------------------------")
             if len(parts) > 1:
                 # Usually the last part is the actual content + emoji
                 clean_result = parts[-1].strip()
                 # Remove leading emoji/space if present (optional but good)
                 if clean_result.startswith("🤖") or clean_result.startswith("✅") or clean_result.startswith("❌") or clean_result.startswith("⚠️"):
                     clean_result = clean_result[1:].strip()

        # Store as "user" with a clear prefix so LLM knows it's system output, not user query
        # This acts as the "Tool Output" block in typical ReAct/Tool patterns
        session_manager.add_message(current_session.id, "user", f"[System Output] {clean_result}")
        
        # Output the result (keep the fancy formatting for the user)
        typer.echo(result_pkg.get("output", ""))
        
    except KeyboardInterrupt:
        typer.echo("\n❌ Operation cancelled by user (Ctrl+C)")
        raise typer.Exit(code=1)
    
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        raise typer.Exit(code=1)
    
    finally:
        if no_confirm:
            safety_module.USE_DETAILED_CONFIRMATION = original_detailed

@app.command(name="server")
def start_server(host: str = "127.0.0.1", port: int = 8080):
    """Start the MCP (Model Context Protocol) server."""
    typer.echo("🚀 Starting MCP Server...")
    try:
        start_mcp_server(host=host, port=port)
    except KeyboardInterrupt:
        typer.echo("\n🛑 MCP Server stopped by user (Ctrl+C)")
    except Exception as e:
        typer.echo(f"❌ Error starting server: {str(e)}")
        raise typer.Exit(code=1)

@app.command(name="k8s-server")
def start_k8s_server(host: str = "127.0.0.1", port: int = 8081):
    """Start the Kubernetes MCP server."""
    typer.echo("🚀 Starting Kubernetes MCP Server...")
    try:
        start_k8s_mcp_server(host=host, port=port)
    except KeyboardInterrupt:
        typer.echo("\n🛑 Kubernetes MCP Server stopped by user (Ctrl+C)")
    except Exception as e:
        typer.echo(f"❌ Error starting server: {str(e)}")
        raise typer.Exit(code=1)

@app.command(name="remote-k8s-server")
def start_remote_k8s_server_cmd(host: str = "127.0.0.1", port: int = 8082):
    """Start the Remote Kubernetes MCP server."""
    from .mcp.remote_k8s_server import start_remote_k8s_mcp_server
    typer.echo("🚀 Starting Remote Kubernetes MCP Server...")
    try:
        start_remote_k8s_mcp_server(host=host, port=port)
    except KeyboardInterrupt:
        typer.echo("\n🛑 Remote K8s Server stopped by user (Ctrl+C)")
    except Exception as e:
        typer.echo(f"❌ Error starting server: {str(e)}")
        raise typer.Exit(code=1)

@app.command(name="start-all")
def start_all_servers():
    """Start all 3 MCP servers in separate console windows."""
    import subprocess
    import sys
    import httpx
    
    typer.echo("🚀 Starting ALL MCP Servers...")
    base_cmd = [sys.executable, "-m", "agentic_docker.cli"]
    
    typer.echo("   • Launching Docker Server (Port 8080)...")
    subprocess.Popen(base_cmd + ["server", "--port", "8080"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    typer.echo("   • Launching Local K8s Server (Port 8081)...")
    subprocess.Popen(base_cmd + ["k8s-server", "--port", "8081"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    typer.echo("   • Launching Remote K8s Server (Port 8082)...")
    subprocess.Popen(base_cmd + ["remote-k8s-server", "--port", "8082"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # ---------------------------------------------------------
    # HOST SELECTION
    # ---------------------------------------------------------
    typer.echo("\n🌐 Ollama Host Selection")
    typer.echo("   Where is your LLM running?")
    typer.echo("   [1] Local (localhost:11434)")
    typer.echo("   [2] Remote / HPC")
    
    host_choice = typer.prompt("\n   Select an option", type=int, default=1)
    
    selected_host = "http://localhost:11434"
    if host_choice == 2:
        selected_host = typer.prompt("   Enter Remote URL", default="http://10.20.39.12:11434")
    
    # Validation
    typer.echo(f"\n   🔍 Verifying connection to {selected_host}...")
    try:
        # Simple health check
        r = httpx.get(f"{selected_host.rstrip('/')}/api/version", timeout=2.0)
        if r.status_code == 200:
             typer.echo("   ✅ Connection successful!")
        else:
             typer.echo(f"   ⚠️  Host reachable but returned status {r.status_code}. Proceeding anyway...")
    except Exception as e:
        typer.echo(f"   ❌ Could not connect to {selected_host}: {e}")
        if not typer.confirm("   Do you want to proceed anyway?", default=False):
            typer.echo("   Aborting start-up.")
            raise typer.Exit(code=1)

    # Save preference
    update_env_file("AGENTIC_LLM_HOST", selected_host)
    
    # ---------------------------------------------------------
    # MODEL SELECTION (HOT SWAP)
    # ---------------------------------------------------------
    typer.echo(f"\n🤖 Model Selection (Configured Host: {selected_host})")
    
    # Reload settings to ensure we pick up the new host (or manually pass it)
    # Since we act dynamically, we can just pass the host to the list function
    from .llm.ollama_client import list_available_models
    
    models = list_available_models(host=selected_host)
    
    if not models:
        typer.echo(f"   ⚠️  No models found on {selected_host}.")
        typer.echo("   Using default configuration from .env")
    else:
        typer.echo("\n   Available Models:")
        for idx, model in enumerate(models, 1):
            typer.echo(f"   {idx}. {model}")
        
        # Default to previous choice if it's in the list
        from .settings import settings
        default_idx = 1
        current_model = settings.LLM_MODEL
        for idx, m in enumerate(models, 1):
             if m == current_model or m.startswith(f"{current_model}:"):
                 default_idx = idx
                 break
        
        choice = typer.prompt("\n   Select a model nr for this session", type=int, default=default_idx)
        
        if 1 <= choice <= len(models):
            selected_model = models[choice - 1]
            update_env_file("AGENTIC_LLM_MODEL", selected_model)
            typer.echo(f"   💾 Saved preference: {selected_model}")
            
            # Visual Confirmation
            typer.echo(f"\n   🚀 Ready! Active Context: [Remote: {selected_model}]" if host_choice == 2 else f"\n   🚀 Ready! Active Context: [Local: {selected_model}]")

    typer.echo("\n✅ All servers launched. You can now run 'agentic-docker run ...'")

def update_env_file(key: str, value: str):
    import os
    env_path = ".env"
    lines = []
    key_found = False
    
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            key_found = True
        else:
            new_lines.append(line)
            
    if not key_found:
        new_lines.append(f"{key}={value}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

@app.command(name="list-tools")
def list_tools():
    """List all available Docker tools."""
    from .tools import get_tools_schema
    from .k8s_tools import get_k8s_tools_schema
    
    typer.echo("📋 Available Tools:")
    
    docker_tools_schema = get_tools_schema()
    typer.echo("\n🐋 Docker Tools:")
    for tool in docker_tools_schema:
        typer.echo(f"• {tool['name']}: {tool['description']}")
    
    k8s_tools_schema = get_k8s_tools_schema()
    typer.echo("\n☸️  Kubernetes Tools:")
    for tool in k8s_tools_schema:
        typer.echo(f"• {tool['name']}: {tool['description']}")
        
@app.callback(invoke_without_command=True)
def cli_entry_callback(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-v", help="Show version and exit")
):
    if version:
        typer.echo("Agentic Docker v1.0.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

def main():
    """Entry point for the console script."""
    app()

if __name__ == "__main__":
    main()