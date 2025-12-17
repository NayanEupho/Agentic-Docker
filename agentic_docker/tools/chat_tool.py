# agentic_docker/tools/chat_tool.py
from typing import Dict, Any
from .base import Tool
from .registry import register_tool

@register_tool
class ChatTool(Tool):
    """
    A simple tool that allows the LLM to "act" by sending a text message.
    This bridges the gap between tool-use enforcement and conversational flow.
    """
    name = "chat"
    description = "Use this tool to reply to the user when no other tool is appropriate (e.g., answering questions, confirming context, or general chat)."
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The text response to send back to the user."
                }
            },
            "required": ["message"]
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Support both direct kwargs and wrapped 'arguments' dict if internal logic differs
        message = kwargs.get("message")
        if not message and "arguments" in kwargs:
             # Fallback if incorrectly called with nested dict
             message = kwargs["arguments"].get("message", "")
             
        if not message:
            message = ""
            
        return {
            "success": True,
            "message": message,
            "display_as_text": True # Hint to formatter
        }
