# devops_agent/mcp/__init__.py
"""
MCP (Model Context Protocol) Subpackage Initialization

This file initializes the MCP subpackage and provides convenient imports
for MCP-related functionality. It makes the MCP components available
for import from the parent package.
"""

# Import key components from the MCP subpackage
from .server import start_mcp_server
from .client import call_tool, test_connection

# Define what gets imported when someone does "from devops_agent.mcp import *"
__all__ = [
    "start_mcp_server",
    "call_tool", 
    "test_connection"
]

# MCP-specific metadata
__version__ = "1.0.0"
__description__ = "Model Context Protocol implementation for Agentic Docker"

def get_mcp_info():
    """
    Get information about the MCP subpackage.
    
    Returns:
        dict: MCP subpackage information
    """
    return {
        "version": __version__,
        "description": __description__,
        "components": ["server", "client"]
    }

# Example usage:
"""
from devops_agent.mcp import start_mcp_server, call_tool
start_mcp_server()  # Start the MCP server
result = call_tool("docker_run_container", {"image": "nginx"})  # Call a tool
"""