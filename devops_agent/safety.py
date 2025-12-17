# devops_agent/safety.py
"""
Safety Layer Module

This module provides user confirmation for potentially destructive operations.
It acts as a guardrail between the LLM's tool calls and actual system changes,
preventing accidental data loss or service interruption.
"""

# Import sys for reading user input
import sys
# Import typing utilities for type hints
from typing import Dict, Any

# Define which tools are considered "dangerous" and require user confirmation
# These are operations that could result in data loss, service interruption, etc.
DANGEROUS_TOOLS = {
    "docker_stop_container",    # Stops running containers
    "docker_run_container",     # Creates new containers (could use resources)
    # Future additions might include:
    # "docker_remove_container", # Removes containers permanently
    # "docker_prune_system",     # Cleans up Docker system (potentially destructive)
}

def confirm_action(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """
    Prompt the user for confirmation before executing a potentially dangerous action.
    
    This function checks if the requested tool is in the dangerous tools list,
    and if so, asks the user to confirm the action before proceeding.
    
    Args:
        tool_name (str): The name of the tool to be executed
        arguments (Dict[str, Any]): The arguments that will be passed to the tool
        
    Returns:
        bool: True if the user confirmed the action, False if they cancelled
    """
    # Check if this tool is considered dangerous
    if tool_name not in DANGEROUS_TOOLS:
        # If not dangerous, proceed without confirmation
        return True
    
    # Display information about the action that's about to be performed
    print(f"\n⚠️  POTENTIALLY DANGEROUS ACTION DETECTED")
    print(f"   Tool: {tool_name}")
    print(f"   Arguments: {arguments}")
    
    # Provide more human-readable information based on the tool type
    if tool_name == "docker_stop_container":
        container_id = arguments.get('container_id', 'unknown')
        print(f"   ⚠️  This will STOP container '{container_id}' and any processes inside it.")
        print(f"   ⚠️  Data in non-persistent volumes may be lost.")
    
    elif tool_name == "docker_run_container":
        image = arguments.get('image', 'unknown')
        ports = arguments.get('ports', {})
        name = arguments.get('name', 'auto-generated')
        print(f"   ℹ️  This will START a new container from image '{image}'")
        if ports:
            print(f"   ℹ️  Port mappings: {ports}")
        if name:
            print(f"   ℹ️  Container name: {name}")
    
    # Ask for user confirmation
    print(f"\n   🤔 Do you want to proceed with this action?")
    print(f"   Type 'yes' to confirm or 'no' to cancel: ", end="")
    
    # Flush the output buffer to ensure the prompt appears immediately
    sys.stdout.flush()
    
    # Read the user's response
    try:
        response = input().strip().lower()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\n   ❌ Action cancelled by user (Ctrl+C)")
        return False
    except EOFError:
        # Handle Ctrl+D or end of input
        print("\n   ❌ Action cancelled (end of input)")
        return False
    
    # Check if the user confirmed
    if response in ['yes', 'y', 'ye', '1', 'true']:
        print(f"   ✅ Action confirmed. Proceeding...")
        return True
    else:
        print(f"   ❌ Action cancelled by user.")
        return False

def add_dangerous_tool(tool_name: str) -> None:
    """
    Add a tool to the dangerous tools list.
    
    This function allows dynamically adding tools to the dangerous list
    at runtime, which can be useful for plugins or extensions.
    
    Args:
        tool_name (str): The name of the tool to mark as dangerous
    """
    DANGEROUS_TOOLS.add(tool_name)
    print(f"   ℹ️  Added '{tool_name}' to dangerous tools list")

def remove_dangerous_tool(tool_name: str) -> None:
    """
    Remove a tool from the dangerous tools list.
    
    This function allows removing tools from the dangerous list,
    though this should be done with caution.
    
    Args:
        tool_name (str): The name of the tool to remove from dangerous list
    """
    DANGEROUS_TOOLS.discard(tool_name)  # discard doesn't raise error if not found
    print(f"   ℹ️  Removed '{tool_name}' from dangerous tools list")

def get_dangerous_tools() -> set:
    """
    Get the current set of dangerous tools.
    
    This function returns the set of tools that currently require confirmation.
    
    Returns:
        set: Set of dangerous tool names
    """
    return DANGEROUS_TOOLS.copy()  # Return a copy to prevent external modification

def is_tool_dangerous(tool_name: str) -> bool:
    """
    Check if a specific tool is considered dangerous.
    
    Args:
        tool_name (str): The name of the tool to check
        
    Returns:
        bool: True if the tool is dangerous, False otherwise
    """
    return tool_name in DANGEROUS_TOOLS

def confirm_action_with_detailed_info(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """
    Enhanced version of confirm_action with more detailed information.
    
    This function provides more context about what the action will do,
    making it easier for users to make informed decisions.
    
    Args:
        tool_name (str): The name of the tool to be executed
        arguments (Dict[str, Any]): The arguments that will be passed to the tool
        
    Returns:
        bool: True if the user confirmed the action, False if they cancelled
    """
    # First check if this tool is dangerous
    if tool_name not in DANGEROUS_TOOLS:
        return True
    
    # Display a more detailed confirmation prompt
    print(f"\n" + "="*60)
    print(f"🚨 DANGEROUS ACTION DETECTED - PLEASE REVIEW CAREFULLY 🚨")
    print("="*60)
    print(f"Tool: {tool_name}")
    print(f"Arguments:")
    for key, value in arguments.items():
        print(f"  - {key}: {value}")
    
    # Provide tool-specific warnings
    if tool_name == "docker_stop_container":
        print(f"\n⚠️  IMPACT:")
        print(f"   • This will immediately stop the container")
        print(f"   • Any unsaved data in non-persistent volumes will be lost")
        print(f"   • Services running in this container will become unavailable")
    
    elif tool_name == "docker_run_container":
        print(f"\n⚠️  IMPACT:")
        print(f"   • This will start a new container that will consume system resources")
        print(f"   • Network ports may be bound, potentially conflicting with other services")
        print(f"   • If a name is provided, it must be unique on this system")
    
    print(f"\n📋 TO PROCEED:")
    print(f"   Type 'CONFIRM' (all caps) to execute this action")
    print(f"   Type anything else to cancel")
    print(f"   Type 'INFO' to see more details about this tool")
    print("-"*60)
    print(f"Your decision: ", end="")
    
    sys.stdout.flush()
    response = input().strip()
    
    if response.upper() == 'CONFIRM':
        print(f"   ✅ Action confirmed and proceeding...")
        return True
    elif response.upper() == 'INFO':
        print(f"\nℹ️  Tool '{tool_name}' details:")
        print(f"   • Purpose: {get_tool_purpose(tool_name)}")
        print(f"   • Arguments: {list(arguments.keys())}")
        print(f"   • Risk level: HIGH")
        # Recursively call this function to show the prompt again
        return confirm_action_with_detailed_info(tool_name, arguments)
    else:
        print(f"   ❌ Action cancelled by user.")
        return False

def get_tool_purpose(tool_name: str) -> str:
    """
    Get a human-readable description of what a tool does.
    
    Args:
        tool_name (str): The name of the tool
        
    Returns:
        str: Description of what the tool does
    """
    purposes = {
        "docker_stop_container": "Stops a running Docker container by ID or name",
        "docker_run_container": "Starts a new Docker container with specified image and configuration",
        "docker_list_containers": "Lists running Docker containers (no confirmation needed)",
    }
    return purposes.get(tool_name, "Unknown tool purpose")

# Configuration: Toggle between simple and detailed confirmation
USE_DETAILED_CONFIRMATION = False

def confirm_action_auto(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """
    Automatic confirmation function that uses the appropriate confirmation method.
    
    Args:
        tool_name (str): The name of the tool to be executed
        arguments (Dict[str, Any]): The arguments that will be passed to the tool
        
    Returns:
        bool: True if the user confirmed the action, False if they cancelled
    """
    if USE_DETAILED_CONFIRMATION:
        return confirm_action_with_detailed_info(tool_name, arguments)
    else:
        return confirm_action(tool_name, arguments)

# Example usage:
"""
if confirm_action("docker_stop_container", {"container_id": "abc123"}):
    # Execute the tool
    result = call_tool("docker_stop_container", {"container_id": "abc123"})
else:
    # Cancelled, don't execute
    print("Action cancelled by user")
"""