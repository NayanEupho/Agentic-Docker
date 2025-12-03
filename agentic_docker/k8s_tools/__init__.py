# agentic_docker/k8s_tools/__init__.py
"""
Kubernetes Tools Registry Module

This module centralizes all available Kubernetes tools, making them easy to import
and manage. It provides functions to get tool schemas (for LLM) and find
specific tools by name (for K8s MCP server). This enables automatic tool discovery
and registration without manual configuration.

This mirrors the structure of the Docker tools registry for consistency.
"""

# Import each individual K8s tool class from its respective file
from .k8s_list_pods import K8sListPodsTool
from .k8s_list_nodes import K8sListNodesTool

# Import typing utilities for type hints
from typing import List, Optional
# Import the base K8sTool class to ensure type safety
from .k8s_base import K8sTool

# Define the list of ALL available Kubernetes tools in the system
# This is the central registry - add new K8s tools here to make them available
ALL_K8S_TOOLS: List[K8sTool] = [
    # Create instances of each K8s tool class
    K8sListPodsTool(),
    K8sListNodesTool(),
    # To add a new K8s tool, simply create its class in a new file
    # and add an instance here, like:
    # K8sGetDeploymentsTool(),
    # K8sGetServicesTool(),
]

def get_k8s_tools_schema() -> List[dict]:
    """
    Generate the JSON Schema for all available Kubernetes tools.
    
    This function collects the parameter schema from each K8s tool and formats
    it in a way that the LLM can understand. The LLM uses this schema
    to know what K8s tools are available and what parameters each accepts.
    
    Returns:
        List[dict]: List of K8s tool schemas in the format expected by LLMs
                   Each schema contains name, description, and parameters
    """
    # Create a list of tool schemas by calling get_parameters_schema()
    # on each K8s tool instance and adding name and description
    return [
        {
            # Tool name (e.g., "k8s_list_pods")
            "name": tool.name,
            # Tool description (e.g., "List Kubernetes pods in a namespace")
            "description": tool.description,
            # Tool parameters schema (from each tool's get_parameters_schema method)
            "parameters": tool.get_parameters_schema()
        }
        # Iterate through all registered K8s tools
        for tool in ALL_K8S_TOOLS
    ]

def find_k8s_tool_by_name(name: str) -> Optional[K8sTool]:
    """
    Find a specific Kubernetes tool by its name.
    
    This function is used by the K8s MCP server to look up which tool to execute
    when the LLM requests a specific tool by name. It returns the tool instance
    so it can be executed with the provided arguments.
    
    Args:
        name (str): The name of the K8s tool to find (e.g., "k8s_list_pods")
    
    Returns:
        Optional[K8sTool]: The K8s tool instance if found, None if not found
    """
    # Loop through all registered K8s tools
    for tool in ALL_K8S_TOOLS:
        # Check if the tool's name matches the requested name
        if tool.name == name:
            # Return the matching tool instance
            return tool
    # If no tool matches, return None
    return None

# Optional: Provide a way to get all K8s tool names (useful for debugging)
def get_all_k8s_tool_names() -> List[str]:
    """
    Get the names of all available Kubernetes tools.
    
    This is primarily useful for debugging and testing to see what K8s tools
    are currently registered in the system.
    
    Returns:
        List[str]: List of all K8s tool names
    """
    return [tool.name for tool in ALL_K8S_TOOLS]

# Optional: Provide a way to check if a K8s tool exists
def k8s_tool_exists(name: str) -> bool:
    """
    Check if a Kubernetes tool with the given name exists in the registry.
    
    Args:
        name (str): The name of the K8s tool to check
    
    Returns:
        bool: True if the K8s tool exists, False otherwise
    """
    return find_k8s_tool_by_name(name) is not None
