# agentic_docker/llm/__init__.py
"""
LLM (Large Language Model) Subpackage Initialization

This file initializes the LLM subpackage and provides convenient imports
for LLM-related functionality. It makes the LLM client components available
for import from the parent package.
"""

# Import key components from the LLM subpackage
from .ollama_client import get_tool_calls, test_llm_connection, ensure_model_exists, list_available_models

# Define what gets imported when someone does "from agentic_docker.llm import *"
__all__ = [
    "get_tool_calls",
    "test_llm_connection", 
    "ensure_model_exists",
    "list_available_models"
]

# LLM-specific metadata
__version__ = "1.0.0"
__description__ = "LLM client implementation for Agentic Docker"

def get_llm_info():
    """
    Get information about the LLM subpackage.
    
    Returns:
        dict: LLM subpackage information
    """
    return {
        "version": __version__,
        "description": __description__,
        "components": ["ollama_client"]
    }

# Example usage:
"""
from agentic_docker.llm import get_tool_calls
tools_schema = [...]  # Your tools schema
tool_calls = get_tool_calls("Start nginx on port 8080", tools_schema)
"""