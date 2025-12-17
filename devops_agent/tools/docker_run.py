# devops_agent/tools/docker_run.py
"""
Docker Run Container Tool

This tool allows the LLM to start new Docker containers with various configurations.
It implements the Tool interface defined in base.py and uses Pydantic for input validation.
"""

# Import the Docker SDK to interact with the Docker daemon
import docker
# Import Pydantic for input validation and data modeling
from pydantic import BaseModel, Field
# Import typing utilities for type hints
from typing import Optional, Dict, List, Any
# Import our base Tool class that this tool must inherit from
from .base import Tool
from .registry import register_tool

class RunContainerArgs(BaseModel):
    """
    Pydantic model for validating the arguments passed to the run container tool.
    
    This ensures that all inputs are properly formatted and safe before
    they're passed to the Docker SDK. Pydantic automatically validates
    the data structure and types.
    """
    
    # Required field: the Docker image to run (e.g., "nginx", "redis:latest")
    image: str = Field(
        ...,  # ... means "required" in Pydantic
        description="The Docker image to run (e.g., 'nginx', 'redis:latest')"
    )
    
    # Optional field: port mappings in format {"host_port": "container_port"}
    # Example: {"8080": "80"} means host port 8080 maps to container port 80
    ports: Optional[Dict[str, str]] = Field(
        None,  # Optional field (can be None)
        description="Port mappings in format {'host_port': 'container_port'}"
    )
    
    # Optional field: custom name for the container
    name: Optional[str] = Field(
        None,  # Optional field
        description="Custom name for the container"
    )
    
    # Optional field: volume mounts in format ["host_path:container_path"]
    # Example: ["/tmp/data:/data"] mounts host's /tmp/data to container's /data
    volumes: Optional[List[str]] = Field(
        None,  # Optional field
        description="Volume mounts in format ['host_path:container_path']"
    )

    from pydantic import model_validator
    
    @model_validator(mode='before')
    @classmethod
    def parse_json_strings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            import json
            # Handle 'ports' being a string "{...}"
            if "ports" in data and isinstance(data["ports"], str):
                try:
                    # If it's literally "{}", just make it empty dict
                    if data["ports"] == "{}":
                        data["ports"] = {}
                    else:
                        data["ports"] = json.loads(data["ports"])
                except json.JSONDecodeError:
                    # If invalid JSON, let Pydantic raise the error normally
                    pass
            
            # Handle 'volumes' being a string "[...]"
            if "volumes" in data and isinstance(data["volumes"], str):
                 try:
                    if data["volumes"] == "{}": # LLM hallucination for empty list
                        data["volumes"] = []
                    elif data["volumes"] == "[]":
                         data["volumes"] = []
                    else:
                        data["volumes"] = json.loads(data["volumes"])
                 except json.JSONDecodeError:
                    pass
        return data

@register_tool
class DockerRunContainerTool(Tool):
    """
    Tool for running new Docker containers.
    
    This tool allows the LLM to start containers with various configurations
    like port mapping, custom names, and volume mounts. It's the most commonly
    used Docker command and demonstrates complex parameter handling.
    """
    
    # Define the unique name for this tool
    name = "docker_run_container"
    
    # Provide a human-readable description of what this tool does
    description = "Run a new Docker container with optional port mapping, name, and volumes"

    def get_parameters_schema(self) -> dict:
        """
        Define the JSON Schema for this tool's parameters.
        
        This tool accepts multiple parameters, all except 'image' are optional:
        - image: string (required) - the Docker image to run
        - ports: object (optional) - port mappings
        - name: string (optional) - custom container name  
        - volumes: array (optional) - volume mounts
        
        The schema follows JSON Schema specification and tells the LLM
        what arguments this tool can accept.
        """
        return {
            "type": "object",
            "properties": {
                # Required: Docker image to run
                "image": {
                    "type": "string",
                    "description": "The Docker image to run (e.g., 'nginx', 'redis:latest')"
                },
                # Optional: Port mappings
                "ports": {
                    "type": "object",
                    "description": "Port mappings in format {'host_port': 'container_port'}",
                    "additionalProperties": {
                        "type": "string"
                    }
                },
                # Optional: Custom container name
                "name": {
                    "type": "string",
                    "description": "Custom name for the container"
                },
                # Optional: Volume mounts
                "volumes": {
                    "type": "array",
                    "description": "Volume mounts in format ['host_path:container_path']",
                    "items": {
                        "type": "string"
                    }
                }
            },
            # 'image' is the only required parameter
            "required": ["image"]
        }

    def run(self, **kwargs) -> dict:
        """
        Execute the actual Docker command to run a container.
        
        This method first validates the input using Pydantic, then connects
        to the Docker daemon and starts the container with the specified
        parameters. It returns structured information about the created container.
        
        Args:
            **kwargs: Parameters passed from the LLM (image, ports, name, volumes)
        
        Returns:
            dict: A structured result containing either:
                  - success: True, container_id: [ID], name: [name], message: [success message]
                  - success: False, error: [error message]
        """
        try:
            # Use Pydantic to validate and parse the arguments
            # This ensures all inputs match our expected format and are safe
            args = RunContainerArgs(**kwargs)
            
            # Connect to the Docker daemon using the default configuration
            client = docker.from_env()
            
            # Start the container using the validated arguments
            # detach=True means the container runs in the background
            # remove=False means we can inspect the container later (good for debugging)
            container = client.containers.run(
                # Required: the Docker image to run
                image=args.image,
                # Optional: port mappings (None if not provided)
                ports=args.ports,
                # Optional: custom container name (None if not provided)
                name=args.name,
                # Optional: volume mounts (None if not provided)
                volumes=args.volumes,
                # Always run in detached mode (background)
                detach=True,
                # Don't auto-remove when container stops (for inspection)
                remove=False
            )
            
            # Return successful result with container information
            return {
                "success": True,
                "container_id": container.short_id,  # Short ID for readability
                "name": container.name,              # Container name (auto-generated if not provided)
                "message": f"Container {container.name} started successfully with image {args.image}."
            }
            
        except Exception as e:
            # If anything goes wrong, catch the exception and return an error
            # This ensures the tool always returns a structured response
            return {
                "success": False,
                "error": str(e),  # Convert exception to string for LLM
                "container_id": None,  # No container ID on error
                "name": None         # No container name on error
            }