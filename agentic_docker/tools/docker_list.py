# agentic_docker/tools/docker_list.py
"""
Docker List Containers Tool

This tool allows the LLM to list Docker containers, either running ones or all containers (including stopped ones).
It implements the Tool interface defined in base.py.
"""

# Import the Docker SDK to interact with the Docker daemon
import docker
# Import our base Tool class that this tool must inherit from
from .base import Tool
from .registry import register_tool

@register_tool
class DockerListContainersTool(Tool):
    """
    Tool for listing Docker containers.
    
    This tool can list either:
    - Only running containers (default behavior, like 'docker ps')
    - All containers (including stopped ones, like 'docker ps -a')
    
    It's the first tool in our system and serves as a template for other tools.
    """
    
    # Define the unique name for this tool
    # This name will be used by the LLM to call this specific tool
    name = "docker_list_containers"
    
    # Provide a human-readable description of what this tool does
    # The LLM will use this description to understand when to use this tool
    description = "List running or all Docker containers"

    def get_parameters_schema(self) -> dict:
        """
        Define the JSON Schema for this tool's parameters.
        
        This tool accepts one optional parameter:
        - 'all': boolean - if True, show all containers (running + stopped)
                 if False or not provided, show only running containers
        
        The schema follows JSON Schema specification and tells the LLM
        what arguments this tool can accept.
        """
        return {
            # This is a JSON Schema object definition
            "type": "object",
            # Properties that the tool accepts
            "properties": {
                # 'all' parameter: boolean type, defaults to False
                "all": {
                    "type": "boolean", 
                    "default": False,  # If not specified, we only list running containers
                    "description": "If true, list all containers (including stopped ones). If false, list only running containers."
                }
            },
            # List of required parameters (empty list means all parameters are optional)
            "required": []
        }

    def run(self, all: bool = False) -> dict:
        """
        Execute the actual Docker command to list containers.
        
        This method connects to the Docker daemon and retrieves container information.
        It then formats the result in a structured way that the LLM can understand.
        
        Args:
            all (bool): If True, include stopped containers in the list.
                       If False (default), only include running containers.
        
        Returns:
            dict: A structured result containing either:
                  - success: True, containers: [list of container info]
                  - success: False, error: [error message]
        """
        try:
            # Connect to the Docker daemon using the default configuration
            # This looks for Docker at standard locations (usually localhost)
            client = docker.from_env()
            
            # Call Docker SDK to list containers
            # The 'all' parameter determines whether to include stopped containers
            # all=True  -> docker ps -a (all containers)
            # all=False -> docker ps (only running containers)
            containers = client.containers.list(all=all)
            
            # Format the container information into a list of dictionaries
            # Each dictionary contains the essential information about a container
            formatted_containers = []
            for container in containers:
                # Create a dictionary with container information
                container_info = {
                    # Short ID (first 12 characters) - easier to read than full ID
                    "id": container.short_id,
                    # Container name - can be auto-generated or user-specified
                    "name": container.name,
                    # Image name - what Docker image the container is based on
                    # Use first tag or 'unknown' if no tags exist
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    # Current status (e.g., "running", "exited", "created")
                    "status": container.status
                }
                # Add this container's info to our list
                formatted_containers.append(container_info)
            
            # Return successful result with the list of containers
            return {
                "success": True,
                "containers": formatted_containers,
                "count": len(formatted_containers)  # Include count for convenience
            }
            
        except Exception as e:
            # If anything goes wrong, catch the exception and return an error
            # This ensures the tool always returns a structured response
            return {
                "success": False,
                "error": str(e),  # Convert exception to string for LLM
                "containers": []  # Empty list on error
            }