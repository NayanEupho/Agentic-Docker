# agentic_docker/mcp/remote_k8s_server.py
"""
Remote Kubernetes MCP Server

This server exposes Kubernetes tools for a remote cluster.
It reads the authentication token from 'token.txt' and configures the tools
to communicate with the remote Kubernetes API.
"""

import os
import sys

# Add the project root to the python path so we can import modules
# This assumes the script is run from the project root or the mcp directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from jsonrpc import JSONRPCResponseManager, dispatcher as k8s_dispatcher
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
from typing import Any, Dict
from agentic_docker.k8s_tools.remote_k8s_tools import find_remote_k8s_tool_by_name, ALL_REMOTE_K8S_TOOLS
from agentic_docker.k8s_tools.k8s_config import k8s_config

def create_k8s_tool_handler(tool_name: str):
    """
    Factory function that creates a JSON-RPC handler for a specific K8s tool.
    """
    def handler(**kwargs) -> Dict[str, Any]:
        tool = find_remote_k8s_tool_by_name(tool_name)
        if tool is None:
            return {
                "success": False,
                "error": f"Remote K8s Tool '{tool_name}' not found in registry"
            }
        try:
            result = tool.run(**kwargs)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Remote K8s tool execution failed: {str(e)}"
            }
    return handler

# Register all Remote K8s tools
for tool in ALL_REMOTE_K8S_TOOLS:
    handler = create_k8s_tool_handler(tool.name)
    k8s_dispatcher.add_method(handler, tool.name)

def k8s_application(environ, start_response):
    """WSGI application function that handles HTTP requests for K8s tools."""
    request = Request(environ)
    request_body = request.get_data(as_text=True)
    response = JSONRPCResponseManager.handle(request_body, k8s_dispatcher)
    wsgi_response = Response(response.json, mimetype='application/json')
    return wsgi_response(environ, start_response)

def load_token(token_path: str = "token.txt") -> str:
    """Load the Bearer token from a file."""
    try:
        with open(token_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: Token file '{token_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading token file: {e}")
        sys.exit(1)

def start_remote_k8s_mcp_server(host: str = '127.0.0.1', port: int = 8082):
    """
    Start the Remote Kubernetes MCP server.
    """
    # Configuration for remote cluster
    REMOTE_API_URL = "https://10.20.4.221:16443"
    TOKEN_FILE = "token.txt"
    
    # Load token
    print(f"Loading token from {TOKEN_FILE}...")
    token = load_token(TOKEN_FILE)
    
    # Configure K8s tools
    print(f"Configuring K8s tools for remote cluster at {REMOTE_API_URL}...")
    k8s_config.configure_remote(
        api_url=REMOTE_API_URL,
        token=token,
        verify_ssl=False  # Assuming self-signed cert or no CA provided
    )
    
    print(f"Remote Kubernetes MCP Server running at http://{host}:{port}")
    print(f"   Target Cluster: {REMOTE_API_URL}")
    print(f"   Available Remote K8s tools: {[tool.name for tool in ALL_REMOTE_K8S_TOOLS]}")
    print("   Press Ctrl+C to stop the server")
    
    run_simple(
        hostname=host,
        port=port,
        application=k8s_application,
        use_reloader=False,
        use_debugger=False,
        threaded=True
    )

if __name__ == "__main__":
    start_remote_k8s_mcp_server()
