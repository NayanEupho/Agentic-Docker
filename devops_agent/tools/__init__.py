# devops_agent/tools/__init__.py
"""
Tools Registry Module

This module centralizes all available Docker tools, making them easy to import
and manage. It provides functions to get tool schemas (for LLM) and find
specific tools by name (for MCP server). This enables automatic tool discovery
and registration without manual configuration.
"""

# Import each individual tool class from its respective file
from .docker_list import DockerListContainersTool
from .docker_run import DockerRunContainerTool
from .docker_stop import DockerStopContainerTool
from .chat_tool import ChatTool

# Import typing utilities for type hints
from typing import List, Optional
# Import the base Tool class to ensure type safety
from .base import Tool

# Import the registry to access registered tools
from .registry import registry

# Define the list of ALL available tools in the system
# This is now dynamically populated from the registry
# We use a property or function call to get the latest list
ALL_TOOLS: List[Tool] = registry.get_tools()

def get_tools_schema() -> List[dict]:
    """
    Generate the JSON Schema for all available tools.
    
    This function collects the parameter schema from each tool and formats
    it in a way that the LLM can understand. The LLM uses this schema
    to know what tools are available and what parameters each accepts.
    
    Returns:
        List[dict]: List of tool schemas in the format expected by LLMs
                   Each schema contains name, description, and parameters
    """
    # Create a list of tool schemas by calling get_parameters_schema()
    # on each tool instance and adding name and description
    return [
        {
            # Tool name (e.g., "docker_list_containers")
            "name": tool.name,
            # Tool description (e.g., "List running or all Docker containers")
            "description": tool.description,
            # Tool parameters schema (from each tool's get_parameters_schema method)
            "parameters": tool.get_parameters_schema()
        }
        # Iterate through all registered tools
        for tool in ALL_TOOLS
    ]

def find_tool_by_name(name: str) -> Optional[Tool]:
    """
    Find a specific tool by its name.
    
    This function is used by the MCP server to look up which tool to execute
    when the LLM requests a specific tool by name. It returns the tool instance
    so it can be executed with the provided arguments.
    
    Args:
        name (str): The name of the tool to find (e.g., "docker_run_container")
    
    Returns:
        Optional[Tool]: The tool instance if found, None if not found
    """
    # Loop through all registered tools
    for tool in ALL_TOOLS:
        # Check if the tool's name matches the requested name
        if tool.name == name:
            # Return the matching tool instance
            return tool
    # If no tool matches, return None
    return None

# Optional: Provide a way to get all tool names (useful for debugging)
def get_all_tool_names() -> List[str]:
    """
    Get the names of all available tools.
    
    This is primarily useful for debugging and testing to see what tools
    are currently registered in the system.
    
    Returns:
        List[str]: List of all tool names
    """
    return [tool.name for tool in ALL_TOOLS]

# Optional: Provide a way to check if a tool exists
def tool_exists(name: str) -> bool:
    """
    Check if a tool with the given name exists in the registry.
    
    Args:
        name (str): The name of the tool to check
    
    Returns:
        bool: True if the tool exists, False otherwise
    """
    return find_tool_by_name(name) is not None