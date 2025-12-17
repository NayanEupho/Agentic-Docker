# agentic_docker/mcp/server.py
"""
MCP (Model Context Protocol) Server

This server exposes Docker tools as JSON-RPC 2.0 methods that can be called
by the LLM. It uses the Werkzeug WSGI server for HTTP handling and the
json-rpc library for JSON-RPC protocol implementation. Each tool from the
tools registry is automatically registered as a callable method.
"""

# Import the JSON-RPC library for handling JSON-RPC 2.0 requests
from jsonrpc import JSONRPCResponseManager, dispatcher
# Import Werkzeug for WSGI server and request handling
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
# Import typing utilities for type hints
from typing import Any, Dict
# Import the tools registry to access all available tools
from ..tools import find_tool_by_name

def create_tool_handler(tool_name: str):
    """
    Factory function that creates a JSON-RPC handler for a specific tool.
    
    This function generates a handler that can be registered with the JSON-RPC
    dispatcher. The handler will look up the tool by name and execute it
    with the provided parameters.
    
    Args:
        tool_name (str): The name of the tool this handler will execute
    
    Returns:
        function: A handler function that can be registered with the dispatcher
    """
    def handler(**kwargs) -> Dict[str, Any]:
        """
        Actual handler function that executes the tool.
        
        This function is called by the JSON-RPC dispatcher when a request
        comes in for the specific tool. It finds the tool, validates parameters,
        executes it, and returns the result.
        
        Args:
            **kwargs: Parameters passed from the JSON-RPC request
            
        Returns:
            Dict[str, Any]: Result of the tool execution
        """
        # Find the tool instance by its name
        tool = find_tool_by_name(tool_name)
        
        # Safety check: if tool doesn't exist, return an error
        if tool is None:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found in registry"
            }
        
        try:
            # Execute the tool with the provided arguments
            # The tool's run method handles validation and execution
            result = tool.run(**kwargs)
            return result
        except Exception as e:
            # If the tool execution fails, return an error
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}"
            }
    
    # Return the handler function
    return handler

# Automatically register all tools from the registry as JSON-RPC methods
# This loop goes through each tool and creates a handler for it
from ..tools import ALL_TOOLS  # Import here to avoid circular imports

for tool in ALL_TOOLS:
    # Create a handler for this specific tool
    handler = create_tool_handler(tool.name)
    # Register the handler with the JSON-RPC dispatcher
    # The method name will be the tool's name (e.g., "docker_run_container")
    dispatcher.add_method(handler, tool.name)

def application(environ, start_response):
    """
    WSGI application function that handles HTTP requests.
    
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
    
    # Handle the JSON-RPC request using the dispatcher
    # This processes the method call and returns the response
    response = JSONRPCResponseManager.handle(request_body, dispatcher)
    
    # Create a Werkzeug Response object with the JSON-RPC response
    # Set the content type to application/json for proper JSON handling
    wsgi_response = Response(response.json, mimetype='application/json')
    
    # Return the response using the WSGI interface
    return wsgi_response(environ, start_response)

# Now loaded from settings.py if not provided
from ..settings import settings

def start_mcp_server(host: str = None, port: int = None):
    """
    Start the MCP server.
    
    This function starts the Werkzeug WSGI server and begins listening
    for JSON-RPC requests. It runs indefinitely until stopped.
    
    Args:
        host (str): The host address to bind to. If None, uses settings.MCP_SERVER_HOST.
        port (int): The port to listen on. If None, uses settings.DOCKER_PORT.
    """
    # Use default settings if arguments are not provided
    if host is None:
        host = settings.MCP_SERVER_HOST
    if port is None:
        port = settings.DOCKER_PORT
    print(f"🚀 MCP Server running at http://{host}:{port}")
    print(f"   Available tools: {[tool.name for tool in ALL_TOOLS]}")
    print("   Press Ctrl+C to stop the server")
    
    # Start the Werkzeug development server
    # This will block and run indefinitely
    run_simple(
        hostname=host,
        port=port,
        application=application,
        # Enable reloader for development (optional)
        use_reloader=False,
        # Enable debugger for development (optional)
        use_debugger=False,
        # Only allow local connections (security)
        threaded=True  # Allow multiple requests simultaneously
    )

# Example of what a JSON-RPC request looks like:
"""
{
    "jsonrpc": "2.0",
    "method": "docker_run_container",
    "params": {
        "image": "nginx",
        "ports": {"8080": "80"}
    },
    "id": 1
}
"""

# Example of what a JSON-RPC response looks like:
"""
{
    "jsonrpc": "2.0",
    "result": {
        "success": true,
        "container_id": "abc123",
        "name": "angry_bell",
        "message": "Container angry_bell started successfully with image nginx."
    },
    "id": 1
}
"""