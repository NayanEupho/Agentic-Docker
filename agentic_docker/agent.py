# agentic_docker/agent.py
"""
Agent Orchestrator

This is the central coordinator that manages the entire flow:
1. Takes user query in natural language
2. Asks LLM to select appropriate tool(s) and parameters
3. Applies safety checks for dangerous operations
4. Executes the tool(s) via MCP client
5. Formats and returns the result(s) to the user

This orchestrates the communication between all system components.
"""

# Import required modules from our project
from .llm.ollama_client import get_tool_calls, ensure_model_exists
from .mcp.client import call_tool, call_k8s_tool, call_remote_k8s_tool, test_connection, test_k8s_connection, test_remote_k8s_connection
from .safety import confirm_action_auto
from .tools import get_tools_schema
from .k8s_tools import get_k8s_tools_schema
from .k8s_tools.remote_k8s_tools import get_remote_k8s_tools_schema
# Import typing utilities for type hints
from typing import Dict, Any, List

def process_query(query: str) -> str:
    """
    Process a user's natural language query and return the result.
    
    This function orchestrates the entire workflow:
    1. Validates system readiness (LLM and MCP server)
    2. Asks LLM to choose appropriate tool(s) and parameters
    3. Applies safety confirmation for dangerous operations
    4. Executes the tool(s) via MCP client
    5. Formats and returns the result(s)
    
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
    
    # 2. Ask LLM to choose tool(s)
    # Now returns a LIST of tool calls
    tool_calls = get_tool_calls(query, all_tools_schema)
    
    if not tool_calls:
        return "❌ I couldn't understand that request or map it to a valid tool. Please try again."
    
    final_results = []
    
    # Iterate through each tool call in the chain
    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]
        
        # 3. Safety Check
        if not confirm_action_auto(tool_name, arguments):
            final_results.append(f"❌ Operation '{tool_name}' cancelled by user.")
            continue
        
        # 4. Execute the tool via appropriate MCP client
        print(f"[INFO] Executing tool {index + 1}/{len(tool_calls)}: {tool_name}")
        
        result = None
        
        # Determine which MCP server to call based on tool name prefix or registry
        if tool_name.startswith("remote_k8s_"):
            result = call_remote_k8s_tool(tool_name, arguments)
        elif tool_name.startswith("k8s_"):
            result = call_k8s_tool(tool_name, arguments)
        else:
            # Default to Docker tools
            result = call_tool(tool_name, arguments)
            
        # 5. Format the result
        formatted_result = format_tool_result(tool_name, result)
        final_results.append(formatted_result)
        
    # Combine all results into a single string
    return "\n\n" + "-"*40 + "\n\n".join(final_results)

def format_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    Helper function to format the result of a single tool execution.
    """
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

        elif tool_name == "remote_k8s_list_namespaces":
            # Special formatting for namespace listing
            namespaces = result.get("namespaces", [])
            count = result.get("count", 0)
            
            if not namespaces:
                return "✅ Success! No namespaces found in REMOTE cluster."
            
            formatted_lines = []
            formatted_lines.append(f"✅ Success! Found {count} namespace(s) in REMOTE cluster:")
            
            for ns in namespaces:
                status_emoji = "🟢" if ns["status"] == "Active" else "🔴"
                line = f"   {status_emoji} {ns['name']} - {ns['status']} [Created: {ns['creation_timestamp']}]"
                formatted_lines.append(line)
                
            return "\n".join(formatted_lines)

        elif tool_name == "remote_k8s_find_pod_namespace":
            # Special formatting for finding pod namespaces
            pod_locations = result.get("pod_locations", {})
            
            if not pod_locations:
                return "✅ Success! No pods queried."
            
            formatted_lines = []
            formatted_lines.append("✅ Success! Pod Location Results (REMOTE):")
            
            for pod_name, location in pod_locations.items():
                if location == "Not Found":
                    line = f"   ❌ {pod_name}: Not Found"
                else:
                    # location is a list of namespaces
                    ns_str = ", ".join(location)
                    line = f"   📍 {pod_name}: Found in namespace(s) -> {ns_str}"
                formatted_lines.append(line)
                
            return "\n".join(formatted_lines)

        elif tool_name == "remote_k8s_get_resources_ips":
            # Special formatting for IP retrieval
            ips = result.get("ips", {})
            
            if not ips:
                return "✅ Success! No resources queried."
            
            formatted_lines = []
            formatted_lines.append("✅ Success! Resource IP Results (REMOTE):")
            
            for name, info in ips.items():
                if info == "Not Found":
                    line = f"   ❌ {name}: Not Found"
                else:
                    # Check if it's a pod or node based on keys
                    if "pod_ip" in info:
                        # It's a pod
                        ports = ", ".join(info.get("ports", []))
                        line = f"   🔹 {name}:\n      - Pod IP: {info.get('pod_ip')}\n      - Host IP: {info.get('host_ip')}\n      - Ports: {ports if ports else 'None'}"
                    else:
                        # It's a node (or generic)
                        details = []
                        for k, v in info.items():
                            details.append(f"{k}: {v}")
                        details_str = "\n      - ".join(details)
                        line = f"   💻 {name}:\n      - {details_str}"
                formatted_lines.append(line)
                
            return "\n".join(formatted_lines)

        elif tool_name == "remote_k8s_list_deployments":
            # Special formatting for deployment listing
            deployments = result.get("deployments", [])
            count = result.get("count", 0)
            scope = result.get("scope", "unknown scope")
            
            if not deployments:
                return f"✅ Success! No deployments found in {scope}."
            
            formatted_lines = []
            formatted_lines.append(f"✅ Success! Found {count} deployment(s) in {scope}:")
            
            # Header
            if "all namespaces" in scope:
                 formatted_lines.append(f"   {'NAMESPACE':<15} {'NAME':<30} {'READY':<10} {'UP-TO-DATE':<12} {'AVAILABLE':<10} {'AGE':<20}")
                 for dep in deployments:
                    name = dep.get('name', 'N/A')
                    ns = dep.get('namespace', 'N/A')
                    ready = f"{dep.get('ready_replicas', 0)}/{dep.get('replicas', 0)}"
                    updated = str(dep.get('updated_replicas', 0))
                    available = str(dep.get('available_replicas', 0))
                    age = dep.get('creation_timestamp', 'N/A')
                    formatted_lines.append(f"   {ns:<15} {name:<30} {ready:<10} {updated:<12} {available:<10} {age:<20}")
            else:
                formatted_lines.append(f"   {'NAME':<30} {'READY':<10} {'UP-TO-DATE':<12} {'AVAILABLE':<10} {'AGE':<20}")
                for dep in deployments:
                    name = dep.get('name', 'N/A')
                    ready = f"{dep.get('ready_replicas', 0)}/{dep.get('replicas', 0)}"
                    updated = str(dep.get('updated_replicas', 0))
                    available = str(dep.get('available_replicas', 0))
                    age = dep.get('creation_timestamp', 'N/A')
                    formatted_lines.append(f"   {name:<30} {ready:<10} {updated:<12} {available:<10} {age:<20}")
                
            return "\n".join(formatted_lines)

        elif tool_name == "remote_k8s_describe_deployment":
            # Special formatting for deployment description
            dep = result.get("deployment", {})
            
            if not dep:
                return "✅ Success! Deployment not found."
            
            formatted_lines = []
            formatted_lines.append(f"✅ Deployment Details: {dep.get('name')} (Namespace: {dep.get('namespace')})")
            formatted_lines.append(f"   📅 Created: {dep.get('creation_timestamp')}")
            formatted_lines.append(f"   🔢 Replicas: {dep.get('replicas_ready')}/{dep.get('replicas_desired')} ready ({dep.get('replicas_updated')} updated, {dep.get('replicas_available')} available)")
            formatted_lines.append(f"   🔄 Strategy: {dep.get('strategy')}")
            
            formatted_lines.append("   📦 Containers:")
            for container in dep.get('containers', []):
                ports = ", ".join([str(p) for p in container.get('ports', [])])
                formatted_lines.append(f"      - {container.get('name')} (Image: {container.get('image')}) [Ports: {ports if ports else 'None'}]")
            
            formatted_lines.append("   🚦 Conditions:")
            for cond in dep.get('conditions', []):
                status_icon = "🟢" if cond.get('status') == "True" else "🔴"
                formatted_lines.append(f"      {status_icon} {cond.get('type')}: {cond.get('message')}")
                
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