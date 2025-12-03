# agentic_docker/mcp/k8s_server.py
"""
Kubernetes MCP (Model Context Protocol) Server

This server exposes Kubernetes tools as JSON-RPC 2.0 methods that can be called
by the LLM. It uses the Werkzeug WSGI server for HTTP handling and the
json-rpc library for JSON-RPC protocol implementation. Each K8s tool from the
k8s_tools registry is automatically registered as a callable method.

This server runs on port 8081 (separate from Docker server on 8080) to maintain
clean separation between Docker and Kubernetes operations.
"""

# Import the JSON-RPC library for handling JSON-RPC 2.0 requests
from jsonrpc import JSONRPCResponseManager, dispatcher as k8s_dispatcher
# Import Werkzeug for WSGI server and request handling
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
# Import typing utilities for type hints
from typing import Any, Dict
# Import the K8s tools registry to access all available K8s tools
from ..k8s_tools import find_k8s_tool_by_name

def create_k8s_tool_handler(tool_name: str):
    """
    Factory function that creates a JSON-RPC handler for a specific K8s tool.
    
    This function generates a handler that can be registered with the JSON-RPC
    dispatcher. The handler will look up the K8s tool by name and execute it
    with the provided parameters.
    
    Args:
        tool_name (str): The name of the K8s tool this handler will execute
    
    Returns:
        function: A handler function that can be registered with the dispatcher
    """
    def handler(**kwargs) -> Dict[str, Any]:
        """
        Actual handler function that executes the K8s tool.
        
        This function is called by the JSON-RPC dispatcher when a request
        comes in for the specific K8s tool. It finds the tool, validates parameters,
        executes it, and returns the result.
        
        Args:
            **kwargs: Parameters passed from the JSON-RPC request
            
        Returns:
            Dict[str, Any]: Result of the tool execution
        """
        # Find the K8s tool instance by its name
        tool = find_k8s_tool_by_name(tool_name)
        
        # Safety check: if tool doesn't exist, return an error
        if tool is None:
            return {
                "success": False,
                "error": f"K8s Tool '{tool_name}' not found in registry"
            }
        
        try:
            # Execute the K8s tool with the provided arguments
            # The tool's run method handles validation and execution
            result = tool.run(**kwargs)
            return result
        except Exception as e:
            # If the tool execution fails, return an error
            return {
                "success": False,
                "error": f"K8s tool execution failed: {str(e)}"
            }
    
    # Return the handler function
    return handler

# Automatically register all K8s tools from the registry as JSON-RPC methods
# This loop goes through each K8s tool and creates a handler for it
from ..k8s_tools import ALL_K8S_TOOLS  # Import here to avoid circular imports

for tool in ALL_K8S_TOOLS:
    # Create a handler for this specific K8s tool
    handler = create_k8s_tool_handler(tool.name)
    # Register the handler with the JSON-RPC dispatcher
    # The method name will be the tool's name (e.g., "k8s_list_pods")
    k8s_dispatcher.add_method(handler, tool.name)

def k8s_application(environ, start_response):
    """
    WSGI application function that handles HTTP requests for K8s tools.
    
    This function is called by the Werkzeug server for each incoming request.
    It parses the JSON-RPC request from the body and passes it to the
    JSON-RPC response manager to handle.
    
    Args:
        environ (dict): WSGI environment dictionary
        start_response (function): WSGI start_response callable
    
    Returns:
        WSGI response iterable
    """
    # Create a Werkzeug Request object from the WSGI environ
    request = Request(environ)
    
    # Get the request body as text
    request_body = request.get_data(as_text=True)
    
    # Handle the JSON-RPC request using the K8s dispatcher
    # This processes the method call and returns the response
    response = JSONRPCResponseManager.handle(request_body, k8s_dispatcher)
    
    # Create a Werkzeug Response object with the JSON-RPC response
    # Set the content type to application/json for proper JSON handling
    wsgi_response = Response(response.json, mimetype='application/json')
    
    # Return the response using the WSGI interface
    return wsgi_response(environ, start_response)

def start_k8s_mcp_server(host: str = '127.0.0.1', port: int = 8081):
    """
    Start the Kubernetes MCP server.
    
    This function starts the Werkzeug WSGI server and begins listening
    for JSON-RPC requests for Kubernetes operations. It runs indefinitely until stopped.
    
    Args:
        host (str): The host address to bind to (default: localhost)
        port (int): The port to listen on (default: 8081 for K8s, vs 8080 for Docker)
    """
    print(f"🚀 Kubernetes MCP Server running at http://{host}:{port}")
    print(f"   Available K8s tools: {[tool.name for tool in ALL_K8S_TOOLS]}")
    print(f"   Kubernetes API Proxy: http://127.0.0.1:8001")
    print("   Press Ctrl+C to stop the server")
    
    # Start the Werkzeug development server
    # This will block and run indefinitely
    run_simple(
        hostname=host,
        port=port,
        application=k8s_application,
        # Enable reloader for development (optional)
        use_reloader=False,
        # Enable debugger for development (optional)
        use_debugger=False,
        # Only allow local connections (security)
        threaded=True  # Allow multiple requests simultaneously
    )

# Example of what a JSON-RPC request looks like for K8s:
"""
{
    "jsonrpc": "2.0",
    "method": "k8s_list_pods",
    "params": {
        "namespace": "default",
        "all_namespaces": false
    },
    "id": 1
}
"""

# Example of what a JSON-RPC response looks like for K8s:
"""
{
    "jsonrpc": "2.0",
    "result": {
        "success": true,
        "pods": [
            {
                "name": "my-pod",
                "namespace": "default",
                "phase": "Running",
                "pod_ip": "10.244.0.5",
                "node": "minikube",
                "containers": 1,
                "ready": "1/1"
            }
        ],
        "count": 1,
        "namespace": "default"
    },
    "id": 1
}
"""
