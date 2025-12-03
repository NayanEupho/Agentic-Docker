# agentic_docker/agent.py
"""
Agent Orchestrator

This is the central coordinator that manages the entire flow:
1. Takes user query in natural language
2. Asks LLM to select appropriate tool and parameters
3. Applies safety checks for dangerous operations
4. Executes the tool via MCP client
5. Formats and returns the result to the user

This orchestrates the communication between all system components.
"""

# Import required modules from our project
from .llm.ollama_client import get_tool_call, ensure_model_exists
from .mcp.client import call_tool, call_k8s_tool, call_remote_k8s_tool, test_connection, test_k8s_connection, test_remote_k8s_connection
from .safety import confirm_action_auto
from .tools import get_tools_schema
from .k8s_tools import get_k8s_tools_schema
from .k8s_tools.remote_k8s_tools import get_remote_k8s_tools_schema
# Import typing utilities for type hints
from typing import Dict, Any

def process_query(query: str) -> str:
    """
    Process a user's natural language query and return the result.
    
    This function orchestrates the entire workflow:
    1. Validates system readiness (LLM and MCP server)
    2. Asks LLM to choose appropriate tool and parameters
    3. Applies safety confirmation for dangerous operations
    4. Executes the tool via MCP client
    5. Formats and returns the result
    
    Args:
        query (str): The user's natural language request
        
    Returns:
        str: Formatted result message for the user
    """
    # 1. Get all available tools schemas
    docker_tools_schema = get_tools_schema()
    k8s_tools_schema = get_k8s_tools_schema()
    remote_k8s_tools_schema = get_remote_k8s_tools_schema()
    
    # Combine all schemas for the LLM
    all_tools_schema = docker_tools_schema + k8s_tools_schema + remote_k8s_tools_schema
    
    # 2. Ask LLM to choose a tool
    tool_call = get_tool_call(query, all_tools_schema)
    
    if not tool_call:
        return "❌ I couldn't understand that request or map it to a valid tool. Please try again."
    
    tool_name = tool_call["name"]
    arguments = tool_call["arguments"]
    
    # 3. Safety Check
    if not confirm_action_auto(tool_name, arguments):
        return "❌ Operation cancelled by user."
    
    # 4. Execute the tool via appropriate MCP client
    print(f"[INFO] Executing tool: {tool_name}")
    
    result = None
    
    # Determine which MCP server to call based on tool name prefix or registry
    if tool_name.startswith("remote_k8s_"):
        result = call_remote_k8s_tool(tool_name, arguments)
    elif tool_name.startswith("k8s_"):
        result = call_k8s_tool(tool_name, arguments)
    else:
        # Default to Docker tools
        result = call_tool(tool_name, arguments)
    
    # 5. Format and return the result
    
    # Check if the operation was successful
    if result.get("success"):
        # Handle successful results differently based on the tool
        if tool_name == "docker_list_containers":
            # Special formatting for container listing
            containers = result.get("containers", [])
            count = result.get("count", 0)
            
            if not containers:
                return "✅ Success! No containers found."
            
            # Format container list nicely
            formatted_lines = []
            formatted_lines.append(f"✅ Success! Found {count} container(s):")
            
            for container in containers:
                status_emoji = get_status_emoji(container["status"])
                line = f"   {status_emoji} {container['name']} ({container['id']}) - {container['image']} [{container['status']}]"
                formatted_lines.append(line)
            
            return "\n".join(formatted_lines)
        
        elif tool_name == "docker_run_container":
            # Special formatting for container creation
            container_id = result.get("container_id", "unknown")
            container_name = result.get("name", "unknown")
            message = result.get("message", f"Container {container_name} started successfully.")
            return f"✅ {message}\n   Container ID: {container_id}\n   Name: {container_name}"
        
        elif tool_name == "docker_stop_container":
            # Special formatting for container stopping
            container_id = result.get("container_id", "unknown")
            container_name = result.get("name", "unknown")
            message = result.get("message", f"Container {container_name} stopped successfully.")
            return f"✅ {message}\n   Container ID: {container_id}\n   Name: {container_name}"
            
        elif tool_name == "k8s_list_pods" or tool_name == "remote_k8s_list_pods":
            # Special formatting for pod listing
            pods = result.get("pods", [])
            count = result.get("count", 0)
            namespace = result.get("namespace", "unknown")
            cluster_type = "REMOTE" if tool_name.startswith("remote_") else "LOCAL"
            
            if not pods:
                return f"✅ Success! No pods found in namespace '{namespace}' ({cluster_type})."
            
            formatted_lines = []
            formatted_lines.append(f"✅ Success! Found {count} pod(s) in namespace '{namespace}' ({cluster_type}):")
            
            for pod in pods:
                status_emoji = "🟢" if pod["phase"] == "Running" else "🔴"
                ready = pod.get("ready", "N/A")
                line = f"   {status_emoji} {pod['name']} ({pod['pod_ip']}) - {pod['phase']} [Ready: {ready}]"
                formatted_lines.append(line)
                
            return "\n".join(formatted_lines)
            
        elif tool_name == "k8s_list_nodes" or tool_name == "remote_k8s_list_nodes":
            # Special formatting for node listing
            nodes = result.get("nodes", [])
            count = result.get("count", 0)
            cluster_type = "REMOTE" if tool_name.startswith("remote_") else "LOCAL"
            
            if not nodes:
                return f"✅ Success! No nodes found ({cluster_type})."
            
            formatted_lines = []
            formatted_lines.append(f"✅ Success! Found {count} node(s) ({cluster_type}):")
            
            for node in nodes:
                status_emoji = "🟢" if node["status"] == "Ready" else "🔴"
                line = f"   {status_emoji} {node['name']} ({node['internal_ip']}) - {node['status']} [Roles: {node['roles']}]"
                formatted_lines.append(line)
                
            return "\n".join(formatted_lines)
        
        else:
            # Generic success message for other tools
            return f"✅ Success! {result.get('message', 'Operation completed successfully.')}"
    
    else:
        # Handle failed operations
        error_msg = result.get("error", "Unknown error occurred")
        return f"❌ Operation failed: {error_msg}"

def get_status_emoji(status: str) -> str:
    """
    Get an appropriate emoji for container status.
    
    Args:
        status (str): The container status (e.g., "running", "exited")
        
    Returns:
        str: An emoji representing the status
    """
    status_map = {
        "running": "🟢",
        "exited": "🔴",
        "created": "🟡",
        "paused": "⏸️",
        "restarting": "🔄",
        "removing": "🧹",
        "dead": "💀"
    }
    return status_map.get(status.lower(), "❓")

def process_query_with_error_handling(query: str) -> str:
    """
    Process a query with comprehensive error handling.
    
    This wrapper function adds an extra layer of error handling
    to catch any unexpected issues during the entire process.
    
    Args:
        query (str): The user's natural language request
        
    Returns:
        str: Formatted result message for the user
    """
    try:
        return process_query(query)
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        return "❌ Operation cancelled by user (Ctrl+C)"
    except Exception as e:
        # Handle any unexpected errors
        return f"❌ Unexpected error occurred: {str(e)}\nPlease check your system and try again."

def get_system_status() -> Dict[str, Any]:
    """
    Get the current status of the system components.
    
    This function checks if all required components are available
    and ready to process queries.
    
    Returns:
        Dict[str, Any]: Status information for LLM, MCP server, and tools
    """
    # Import the MODEL constant from the ollama client to ensure consistency
    from .llm.ollama_client import MODEL
    
    llm_available = ensure_model_exists()
    mcp_available = test_connection()
    k8s_mcp_available = test_k8s_connection()
    remote_k8s_available = test_remote_k8s_connection()
    
    # Get tools schemas
    docker_tools = [tool['name'] for tool in get_tools_schema()]
    k8s_tools = [tool['name'] for tool in get_k8s_tools_schema()]
    remote_k8s_tools = [tool['name'] for tool in get_remote_k8s_tools_schema()]
    
    return {
        "llm": {
            "available": llm_available,
            # Use the actual configured model name from ollama_client.py, not hardcoded
            "model": MODEL
        },
        "docker_mcp_server": {
            "available": mcp_available,
            "url": "http://127.0.0.1:8080"
        },
        "k8s_mcp_server": {
            "available": k8s_mcp_available,
            "url": "http://127.0.0.1:8081"
        },
        "remote_k8s_mcp_server": {
            "available": remote_k8s_available,
            "url": "http://127.0.0.1:8082"
        },
        "tools": {
            "available": docker_tools + k8s_tools + remote_k8s_tools,
            "count": len(docker_tools) + len(k8s_tools) + len(remote_k8s_tools),
            "docker": docker_tools,
            "kubernetes": k8s_tools,
            "remote_kubernetes": remote_k8s_tools
        }
    }

def process_query_with_status_check(query: str) -> str:
    """
    Process a query with pre-check of system status.
    
    This function checks system status before processing the query
    and provides helpful error messages if components are unavailable.
    
    Args:
        query (str): The user's natural language request
        
    Returns:
        str: Formatted result message for the user
    """
    status = get_system_status()
    
    if not status["llm"]["available"]:
        return f"❌ LLM not available. Please ensure Ollama is running and model '{status['llm']['model']}' is installed."
    
    if not status["docker_mcp_server"]["available"] and not status["k8s_mcp_server"]["available"] and not status["remote_k8s_mcp_server"]["available"]:
         return f"❌ No MCP servers available. Please start at least one server."
    
    if status["tools"]["count"] == 0:
        return f"❌ No tools available. Please check your tool configuration."
    
    # If all systems are go, process the query normally
    return process_query_with_error_handling(query)