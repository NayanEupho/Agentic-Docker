# agentic_docker/k8s_tools/__init__.py
"""
Kubernetes Tools Registry Module

This module centralizes all available Kubernetes tools, making them easy to import
and manage. It provides functions to get tool schemas (for LLM) and find
specific tools by name (for K8s MCP server). This enables automatic tool discovery
and registration without manual configuration.

This mirrors the structure of the Docker tools registry for consistency.
"""

# Import each individual K8s tool class
from .k8s_base import K8sTool
from .local_k8s_list_pods import LocalK8sListPodsTool
from .local_k8s_list_nodes import LocalK8sListNodesTool
from .remote_k8s_tools import ALL_REMOTE_K8S_TOOLS

# Import typing utilities for type hints
from typing import List, Optional

# Export the tools list
ALL_LOCAL_K8S_TOOLS = [
    LocalK8sListPodsTool(),
    LocalK8sListNodesTool(),
]

# Define the list of ALL available Kubernetes tools in the system
# This is the central registry - add new K8s tools here to make them available
# (Combined list for helper functions)
def get_all_tools():
    return ALL_LOCAL_K8S_TOOLS + ALL_REMOTE_K8S_TOOLS

def get_k8s_tools_schema() -> List[dict]:
    """
    Generate the JSON Schema for all available Kubernetes tools.
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.get_parameters_schema()
        }
        for tool in get_all_tools()
    ]

def find_k8s_tool_by_name(name: str) -> Optional[K8sTool]:
    """
    Find a specific Kubernetes tool by its name.
    """
    for tool in get_all_tools():
        if tool.name == name:
            return tool
    return None

def get_all_k8s_tool_names() -> List[str]:
    """
    Get the names of all available Kubernetes tools.
    """
    return [tool.name for tool in get_all_tools()]

def k8s_tool_exists(name: str) -> bool:
    """
    Check if a Kubernetes tool with the given name exists in the registry.
    """
    return find_k8s_tool_by_name(name) is not None
