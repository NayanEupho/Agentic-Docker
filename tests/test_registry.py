import pytest
from agentic_docker.tools.base import Tool
from agentic_docker.tools.registry import ToolRegistry, register_tool

# Mock Tool 1
class MockTool1(Tool):
    name = "mock_tool_1"
    description = "Mock tool 1"
    def get_parameters_schema(self): return {}
    def run(self, **kwargs): return {}

# Mock Tool 2 (for decorator)
class MockTool2(Tool):
    name = "mock_tool_2"
    description = "Mock tool 2"
    def get_parameters_schema(self): return {}
    def run(self, **kwargs): return {}

def test_manual_registration():
    registry = ToolRegistry()
    registry.register(MockTool1)
    
    tools = registry.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "mock_tool_1"
    assert registry.get_tool("mock_tool_1") is tools[0]

def test_decorator_registration():
    # We need a fresh registry for this test usually, but our logic uses a global one in the module.
    # We can inspect the global one or create a scoped one if we could.
    # For unit testing the logic, we can just test the decorator mechanism.
    
    registry = ToolRegistry()
    
    # Define a custom decorator that uses our local registry
    def local_register_tool(cls):
        registry.register(cls)
        return cls
        
    @local_register_tool
    class DecoratedTool(Tool):
        name = "decorated_tool"
        description = "Decorated"
        def get_parameters_schema(self): return {}
        def run(self, **kwargs): return {}
        
    tools = registry.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "decorated_tool"

def test_get_unknown_tool():
    registry = ToolRegistry()
    assert registry.get_tool("nonexistent") is None
