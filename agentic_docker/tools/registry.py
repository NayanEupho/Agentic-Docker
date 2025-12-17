from typing import Dict, List, Type, Any
from .base import Tool

class ToolRegistry:
    """
    Central registry for all available tools.
    Allows tools to register themselves via decorators.
    """
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool_cls: Type[Tool]):
        """
        Register a tool class. Instantiate it and add to registry.
        """
        tool_instance = tool_cls()
        self._tools[tool_instance.name] = tool_instance
        return tool_cls

    def get_tools(self) -> List[Tool]:
        """
        Get all registered tools.
        """
        return list(self._tools.values())

    def get_tool(self, name: str) -> Tool:
        """
        Get a specific tool by name.
        """
        return self._tools.get(name)

# Global registry instance
registry = ToolRegistry()

def register_tool(cls):
    """
    Decorator to register a tool class.
    
    Usage:
        @register_tool
        class MyTool(Tool):
            ...
    """
    registry.register(cls)
    return cls
