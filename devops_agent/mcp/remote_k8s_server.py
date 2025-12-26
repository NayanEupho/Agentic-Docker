# devops_agent/mcp/remote_k8s_server.py
"""
Remote Kubernetes MCP Server

This server exposes Kubernetes tools for a remote cluster.
It reads the authentication token from 'token.txt' and configures the tools
to communicate with the remote Kubernetes API.
"""

import os
import sys
import warnings
import urllib3

# Suppress SSL warnings for self-signed certs (common in K8s clusters)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Add the project root to the python path so we can import modules
# This assumes the script is run from the project root or the mcp directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from jsonrpc import JSONRPCResponseManager, dispatcher as k8s_dispatcher
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
from typing import Any, Dict
from devops_agent.k8s_tools.remote_k8s_tools import find_remote_k8s_tool_by_name, ALL_REMOTE_K8S_TOOLS
from devops_agent.k8s_tools.k8s_config import k8s_config
from devops_agent.settings import settings

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
    # Loaded from settings
    
    # Load token
    print(f"Loading token from {settings.REMOTE_K8S_TOKEN_PATH}...")
    token = load_token(settings.REMOTE_K8S_TOKEN_PATH)
    
    # Configure K8s tools
    print(f"Configuring K8s tools for remote cluster at {settings.REMOTE_K8S_API_URL}...")
    k8s_config.configure_remote(
        api_url=settings.REMOTE_K8S_API_URL,
        token=token,
        verify_ssl=settings.REMOTE_K8S_VERIFY_SSL
    )
    
    print(f"🚀 Remote Kubernetes MCP Server running at http://{host}:{port}")
    print(f"   Available Remote K8s tools: {[tool.name for tool in ALL_REMOTE_K8S_TOOLS]}")
    print(f"   Target Cluster: {settings.REMOTE_K8S_API_URL}")
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
