# devops_agent/cli.py
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
from .mcp.docker_server import start_mcp_server
# Import the K8s MCP server function
from .mcp.local_k8s_server import start_k8s_mcp_server
# Import system status function
# Import system status function
from .agent import get_system_status
import os

# --- PROXY CONFIGURATION ---
# Ensure localhost traffic bypasses any conflicting proxies
# The user (Nayan) has a proxy at 10.20.4.125:3128
current_no_proxy = os.environ.get("NO_PROXY", "")
needed_entries = ["localhost", "127.0.0.1"]
updates = []
for entry in needed_entries:
    if entry not in current_no_proxy:
        updates.append(entry)

if updates:
    if current_no_proxy:
        os.environ["NO_PROXY"] = f"{current_no_proxy},{','.join(updates)}"
    else:
        os.environ["NO_PROXY"] = ",".join(updates)
# ---------------------------

# Create the main Typer application instance
app = typer.Typer(
    name="devops-agent",
    help="An AI-powered DevOps Agent that understands natural language commands.",
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
    typer.echo("   Run 'devops-agent session end' to stop.")

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
        if not force:
            if not typer.confirm("Are you sure you want to DELETE ALL history?"):
                return
        session_manager.clear_all()
        typer.echo("✅ All history deleted.")


@app.command(
    name="chat",
    help="Start an interactive chat session with DevOps Agent."
)
def chat_command(
    session_name: Optional[str] = typer.Option(
        None,
        "--session",
        help="Start a NEW session with this specific title/name"
    ),
    session_resume: Optional[str] = typer.Option(
        None,
        "--session-resume",
        help="Resume an EXISTING session by ID"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show details"),
):
    """
    Start an interactive chat session (REPL).
    Type 'exit', 'quit', or '/bye' to end the session.
    """
    from .database.session_manager import session_manager
    from .cli_helper import process_command_turn
    from .settings import settings
    
    # 1. Session Setup
    current_session = None
    
    if session_name:
        # Create NEW named session
        current_session = session_manager.create_session(title=session_name)
        typer.echo(f"✨ Created NEW session: '{session_name}' (ID: {current_session.id})")
        
    elif session_resume:
        # Resume EXISTING session
        current_session = session_manager.get_session(session_resume)
        if not current_session:
            typer.echo(f"❌ Session ID '{session_resume}' not found.")
            raise typer.Exit(code=1)
        typer.echo(f"🔙 Resumed session: '{current_session.title or session_resume}'")
        
        # Re-print last few messages for context?
        if current_session.messages:
            last_msg = current_session.messages[-1]
            typer.echo(f"   Last message ({last_msg.role}): {last_msg.content[:100]}...")

    else:
        # Default: Create NEW unnamed session
        current_session = session_manager.create_session()
        typer.echo(f"✨ Started new chat session (ID: {current_session.id})")
    
    # Set as active
    session_manager.set_active_session(current_session.id)
    
    # 2. Welcome Banner
    host_label = "Remote" if "localhost" not in settings.LLM_HOST and "127.0.0.1" not in settings.LLM_HOST else "Local"
    typer.echo(f"\n🤖 DevOps Agent Interactive Mode [{host_label} | {settings.LLM_MODEL}]")
    typer.echo("   Type 'exit', 'quit', or Ctrl+C to leave.")
    typer.echo("-" * 50)
    
    # 3. REPL Loop
    try:
        import readline  # For history/arrow keys support (on Linux/Mac)
    except ImportError:
        pass  # Readline not available (e.g. Windows), history features will be disabled
    
    while True:
        try:
            # Custom prompt
            query = typer.prompt(f"[{host_label}] >>>", prompt_suffix=" ")
            
            # Check exit conditions
            if query.strip().lower() in ["exit", "quit", "/bye", "bye"]:
                typer.echo("👋 Goodbye!")
                break
                
            if not query.strip():
                continue
            
            # Process
            process_command_turn(
                session=current_session,
                query=query,
                verbose=verbose,
                no_confirm=False, # Interactive mode usually implies you can confirm, but let's default to standard safety
                check_llm=False
            )
            
            # Refresh session to ensure we have latest state if needed
            # (session object is passed by reference-ish but `session_manager` updates DB)
            # We don't strictly need to reload `current_session` object unless we access properties that change.
            
        except KeyboardInterrupt:
            typer.echo("\n👋 Exiting chat...")
            break
        except Exception as e:
            typer.echo(f"❌ Error: {e}")
            # Don't crash the loop



@app.command(
    name="run",
    help="Execute a DevOps command in natural language."
)
def run_command(
    query: str = typer.Argument(
        ...,
        help="Your natural language request (e.g., 'Start nginx on port 8080')"
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
        import devops_agent.safety as safety_module
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
        
        # Use shared helper
        from .cli_helper import process_command_turn
        process_command_turn(
            session=current_session,
            query=query,
            verbose=verbose,
            no_confirm=no_confirm,
            check_llm=check_llm
        )
        
    except KeyboardInterrupt:
        typer.echo("\n❌ Operation cancelled by user (Ctrl+C)")
        raise typer.Exit(code=1)
    
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        raise typer.Exit(code=1)

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
    
    # helper for wizard flow
    def select_provider_flow(label: str, default_host: str = "http://localhost:11434") -> tuple[str, str]:
        """
        Interactive wizard to select a Host and a Model.
        Returns: (selected_host, selected_model)
        """
        from .llm.ollama_client import list_available_models, pull_model, check_model_access
        
        typer.echo(f"\n{label}")
        typer.echo("   Where is this LLM running?")
        typer.echo("   [1] Local (localhost:11434)")
        typer.echo("   [2] Remote / HPC")
        typer.echo("   [3] Custom URL")
        
        msg = "   Select Host"
        
        host_choice = typer.prompt(msg, default=1)
        
        selected_host = "http://localhost:11434"
        if str(host_choice) == "2":
            selected_host = typer.prompt("   Enter Remote URL", default="http://10.20.39.12:11434")
        elif str(host_choice) == "3":
            selected_host = typer.prompt("   Enter Custom URL", default=default_host)
        else:
            # If they just hit enter on default=1
            if str(host_choice) == "1":
                 selected_host = "http://localhost:11434"

        # Validation
        typer.echo(f"   🔍 Verifying connection to {selected_host}...")
        try:
            r = httpx.get(f"{selected_host.rstrip('/')}/api/version", timeout=2.0)
            if r.status_code == 200:
                 typer.echo("   ✅ Connection successful!")
            else:
                 typer.echo(f"   ⚠️  Host reachable but returned status {r.status_code}.")
        except Exception as e:
            typer.echo(f"   ❌ Could not connect to {selected_host}: {e}")
            if not typer.confirm("   Do you want to proceed anyway?", default=False):
                return None, None

        # Model Loop
        while True:
            try:
                typer.echo(f"\n   Fetching models from {selected_host}...")
                models = list_available_models(host=selected_host)
                models.sort()
                
                typer.echo(f"\n   Available Models ({len(models)}):")
                for i, m in enumerate(models):
                    typer.echo(f"   [{i+1}] {m}")
                
                typer.echo(f"   [{len(models)+1}] ➕ Download/Pull New Model")
                typer.echo(f"   [{len(models)+2}] Custom / Manually Enter Name")
                
                choice = typer.prompt(f"\n   Select Model (1-{len(models)+2})", type=int, default=1)
                
                if choice == len(models) + 1:
                    # Download
                    new_model = typer.prompt("   Enter model name to pull (e.g. llama3:8b)")
                    if pull_model(new_model, host=selected_host):
                        typer.echo("   Refreshing list...")
                        continue # Loop back to list
                    else:
                        typer.echo("   ❌ Pull failed. Try another or check logs.")
                        continue
                        
                elif choice == len(models) + 2:
                    # Custom Manual
                    custom_model = typer.prompt("   Enter model name manually")
                    return selected_host, custom_model
                    
                elif 1 <= choice <= len(models):
                    # Selected
                    model = models[choice-1]
                    
                    # Validation check
                    typer.echo(f"   🔍 Checking access to '{model}'...")
                    if check_model_access(selected_host, model):
                        typer.echo("   ✅ Verified!")
                    else:
                         typer.echo("   ⚠️  Model selected but seems unresponsive.")
                    
                    return selected_host, model
                else:
                     typer.echo("   Invalid choice.")
                     
            except Exception as e:
                 typer.echo(f"   ⚠️ Error fetching models: {e}")
                 if typer.confirm("   Retry?", default=True):
                     continue
                 else:
                     return selected_host, typer.prompt("   Enter model name manually")

    # ---------------------------------------------------------
    # 1. SMART MODEL CONFIGURATION
    # ---------------------------------------------------------
    smart_host, smart_model = select_provider_flow("🤖 Smart Model Configuration (Primary)")
    if not smart_host or not smart_model:
        typer.echo("❌ Configuration aborted.")
        raise typer.Exit(1)
        
    update_env_file("DEVOPS_LLM_HOST", smart_host)
    update_env_file("DEVOPS_LLM_MODEL", smart_model)
    
    # ---------------------------------------------------------
    # 2. FAST MODEL CONFIGURATION
    # ---------------------------------------------------------
    typer.echo(f"\n⚡ Fast Model Configuration")
    
    fast_host = smart_host
    fast_model = smart_model
    
    if typer.confirm("   Configure a different Fast Model? (Recommended for speed)", default=False):
        # Check if we want to use the same host or different host
        # Actually, let's just use the wizard. It allows selecting 'Local' easily.
        
        # Pre-calculate default host: likely local if smart was remote
        default_fast_host = "http://localhost:11434"
        
        f_host, f_model = select_provider_flow("⚡ Fast Model Setup", default_host=default_fast_host)
        if f_host and f_model:
            fast_host = f_host
            fast_model = f_model
            update_env_file("DEVOPS_LLM_FAST_HOST", fast_host)
            update_env_file("DEVOPS_LLM_FAST_MODEL", fast_model)
    else:
        # Use same as smart
        typer.echo("   -> Using same configuration as Smart Model.")
        update_env_file("DEVOPS_LLM_FAST_HOST", "") # Empty means fallback to primary
        update_env_file("DEVOPS_LLM_FAST_MODEL", "")

    # ---------------------------------------------------------
    # 3. SUMMARY
    # ---------------------------------------------------------
    typer.echo("\n" + "="*50)
    typer.echo("✅ Configuration Complete:")
    typer.echo(f"🧠 Smart Model: {smart_model} @ {smart_host}")
    typer.echo(f"⚡ Fast Model:  {fast_model} @ {fast_host}")
    typer.echo("="*50 + "\n")

    # ---------------------------------------------------------
    # 4. START SERVERS
    # ---------------------------------------------------------
    typer.echo("🚀 Starting ALL MCP Servers...")
    base_cmd = [sys.executable, "-m", "devops_agent.cli"]
    
    typer.echo("   • Launching Docker Server (Port 8080)...")
    subprocess.Popen(base_cmd + ["server", "--port", "8080"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    typer.echo("   • Launching Local K8s Server (Port 8081)...")
    subprocess.Popen(base_cmd + ["k8s-server", "--port", "8081"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    typer.echo("   • Launching Remote K8s Server (Port 8082)...")
    subprocess.Popen(base_cmd + ["remote-k8s-server", "--port", "8082"], creationflags=subprocess.CREATE_NEW_CONSOLE)

    typer.echo("\n✨ All servers are running! Run 'devops-agent chat' to start.")

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
        typer.echo("DevOps Agent v1.0.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

def main():
    """Entry point for the console script."""
    app()

if __name__ == "__main__":
    main()