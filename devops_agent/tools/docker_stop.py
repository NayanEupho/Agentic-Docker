# devops_agent/tools/docker_stop.py
"""
Docker Stop Container Tool

This tool allows the LLM to stop running Docker containers by ID or name.
It implements the Tool interface defined in base.py and uses Pydantic for input validation.
"""

# Import the Docker SDK to interact with the Docker daemon
import docker
# Import Pydantic for input validation and data modeling
from pydantic import BaseModel, Field
# Import typing utilities for type hints
from typing import Dict, Any
# Import our base Tool class that this tool must inherit from
from .base import Tool
from .registry import register_tool

class StopContainerArgs(BaseModel):
    """
    Pydantic model for validating the arguments passed to the stop container tool.
    
    This tool requires only the container ID or name to identify which container
    to stop. Pydantic ensures this parameter is provided and properly formatted.
    """
    
    # Required field: the container ID or name to stop
    container_id: str = Field(
        ...,  # ... means "required" in Pydantic
        description="The ID or name of the container to stop"
    )

@register_tool
class DockerStopContainerTool(Tool):
    """
    Tool for stopping Docker containers.
    
    This tool allows the LLM to stop a running container by its ID or name.
    It's a destructive operation (stops the container), so it's marked as
    dangerous in the safety layer and requires user confirmation.
    """
    
    # Define the unique name for this tool
    name = "docker_stop_container"
    
    # Provide a human-readable description of what this tool does
    description = "Stop a running Docker container by ID or name"

    def get_parameters_schema(self) -> dict:
        """
        Define the JSON Schema for this tool's parameters.
        
        This tool accepts only one required parameter:
        - container_id: string - the ID or name of the container to stop
        
        The schema follows JSON Schema specification and tells the LLM
        what arguments this tool can accept.
        """
        return {
            "type": "object",
            "properties": {
                # Required: Container ID or name to stop
                "container_id": {
                    "type": "string",
                    "description": "The ID or name of the container to stop"
                }
            },
            # container_id is required
            "required": ["container_id"]
        }

    def run(self, **kwargs) -> dict:
        """
        Execute the actual Docker command to stop a container.
        
        This method first validates the input using Pydantic, then connects
        to the Docker daemon and stops the specified container.
        It returns structured information about the operation result.
        
        Args:
            **kwargs: Parameters passed from the LLM (container_id)
        
        Returns:
            dict: A structured result containing either:
                  - success: True, message: [success message]
                  - success: False, error: [error message]
        """
        try:
            # Use Pydantic to validate and parse the arguments
            # This ensures the container_id is provided and is a string
            args = StopContainerArgs(**kwargs)
            
            # Connect to the Docker daemon using the default configuration
            client = docker.from_env()
            
            # Get the container by ID or name
            # This can accept either the short ID, full ID, or container name
            container = client.containers.get(args.container_id)
            
            # Stop the container
            # This sends a SIGTERM signal to the container to stop it gracefully
            container.stop()
            
            # Return successful result
            return {
                "success": True,
                "container_id": container.short_id,  # Return the ID of the stopped container
                "name": container.name,              # Return the name of the stopped container
                "message": f"Container {container.name} (ID: {container.short_id}) stopped successfully."
            }
            
        except docker.errors.NotFound:
            # Handle the case where the container doesn't exist
            return {
                "success": False,
                "error": f"Container '{args.container_id}' not found. It may have already been stopped or removed.",
                "container_id": args.container_id
            }
            
        except docker.errors.APIError as e:
            # Handle Docker API errors (e.g., permission issues, invalid requests)
            return {
                "success": False,
                "error": f"Docker API error: {str(e)}",
                "container_id": args.container_id
            }
            
        except Exception as e:
            # Handle any other unexpected errors
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "container_id": args.container_id
            }