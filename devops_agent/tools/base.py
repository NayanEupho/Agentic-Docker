# devops_agent/tools/base.py
"""
Base class for all Docker tools.

This defines the standard interface that all tools must implement.
It ensures consistency across different Docker operations.
"""

# Import the Abstract Base Class (ABC) module
# This allows us to define abstract methods that must be implemented by subclasses
from abc import ABC, abstractmethod
from typing import Dict, Any

class Tool(ABC):
    """
    Abstract base class for all Docker tools.
    
    Every Docker command that we want to support must inherit from this class.
    This ensures that all tools have the same structure and behavior.
    """
    
    # These are class attributes that subclasses must define
    name: str  # Unique identifier for the tool (e.g., "docker_run_container")
    description: str  # Human-readable description of what the tool does

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Return the JSON Schema for this tool's parameters.
        
        This schema tells the LLM what arguments the tool accepts.
        For example, a 'run' tool might accept 'image', 'ports', 'name', etc.
        
        Returns:
            Dict[str, Any]: JSON Schema describing the tool's parameters
        """
        pass  # This method must be implemented by subclasses

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the actual Docker command.
        
        This method performs the real work (e.g., starts a container, stops one, etc.)
        It should always return a dictionary with a 'success' key to indicate
        whether the operation worked.
        
        Args:
            **kwargs: Parameters passed from the LLM (validated by Pydantic)
            
        Returns:
            Dict[str, Any]: Result of the operation with 'success' status
        """
        pass  # This method must be implemented by subclasses