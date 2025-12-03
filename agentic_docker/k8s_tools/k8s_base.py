# agentic_docker/k8s_tools/k8s_base.py
"""
Base class for all Kubernetes tools.

This defines the standard interface that all K8s tools must implement.
It ensures consistency across different Kubernetes operations and mirrors
the structure used by Docker tools.
"""

# Import the Abstract Base Class (ABC) module
# This allows us to define abstract methods that must be implemented by subclasses
from abc import ABC, abstractmethod
from typing import Dict, Any

class K8sTool(ABC):
    """
    Abstract base class for all Kubernetes tools.
    
    Every Kubernetes command that we want to support must inherit from this class.
    This ensures that all K8s tools have the same structure and behavior.
    """
    
    # These are class attributes that subclasses must define
    name: str  # Unique identifier for the tool (e.g., "k8s_list_pods")
    description: str  # Human-readable description of what the tool does

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Return the JSON Schema for this tool's parameters.
        
        This schema tells the LLM what arguments the tool accepts.
        For example, a 'list pods' tool might accept 'namespace', 'all_namespaces', etc.
        
        Returns:
            Dict[str, Any]: JSON Schema describing the tool's parameters
        """
        pass  # This method must be implemented by subclasses

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the actual Kubernetes command.
        
        This method performs the real work (e.g., lists pods, lists nodes, etc.)
        It should always return a dictionary with a 'success' key to indicate
        whether the operation worked.
        
        Args:
            **kwargs: Parameters passed from the LLM (validated by schema)
            
        Returns:
            Dict[str, Any]: Result of the operation with 'success' status
        """
        pass  # This method must be implemented by subclasses
