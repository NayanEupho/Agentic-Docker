# agentic_docker/mcp/client.py
"""
MCP (Model Context Protocol) Client

This client sends JSON-RPC 2.0 requests to the MCP server to execute Docker tools.
It handles the communication protocol, request formatting, and response parsing.
The client is used by the agent to execute tools chosen by the LLM.
"""

# Import the requests library for HTTP communication
import requests
# Import JSON library for handling JSON data
import json
# Import typing utilities for type hints
from typing import Dict, Any, Optional

# Configuration: The URL where the MCP server is running
# This should match the server's host and port
MCP_URL = "http://127.0.0.1:8080"
# Kubernetes MCP server (for k8s_* tools)
K8S_MCP_URL = "http://127.0.0.1:8081"
# Remote Kubernetes MCP server (for remote_k8s_* tools)
REMOTE_K8S_MCP_URL = "http://127.0.0.1:8082"

def call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a JSON-RPC request to the MCP server to execute a specific tool.
    
    This function formats the tool call as a JSON-RPC 2.0 request, sends it
    to the server, and returns the response. It handles the communication
    protocol between the client and server.
    
    Args:
        tool_name (str): The name of the tool to execute (e.g., "docker_run_container")
        arguments (Dict[str, Any]): The parameters to pass to the tool
        
    Returns:
        Dict[str, Any]: The result from the tool execution, containing:
                       - success: bool - whether the operation succeeded
                       - Other fields depending on the specific tool
    """
    # Create the JSON-RPC 2.0 request payload
    # This follows the JSON-RPC 2.0 specification
    payload = {
        # JSON-RPC protocol version
        "jsonrpc": "2.0",
        # The method to call (this should match a registered tool name)
        "method": tool_name,
        # Parameters to pass to the method
        "params": arguments,
        # Request ID for matching responses to requests (optional but recommended)
        "id": 1
    }
    
    try:
        # Send the JSON-RPC request to the MCP server
        # Use POST method with JSON content type
        response = requests.post(
            url=MCP_URL,
            # Send the payload as JSON
            json=payload,
            # Set a reasonable timeout to prevent hanging
            timeout=30,
            # Specify content type (though requests.json does this automatically)
            headers={'Content-Type': 'application/json'}
        )
        
        # Check if the HTTP request was successful (status code 200-299)
        response.raise_for_status()
        
        # Parse the JSON response from the server
        result = response.json()
        
        # Handle the case where the server returns a JSON-RPC error
        if "error" in result:
            # Return an error result if the server reported an error
            return {
                "success": False,
                "error": result["error"],
                "original_response": result  # Include original error for debugging
            }
        
        # Return the result from the tool execution
        # This will contain the actual tool output (e.g., container info, success message)
        return result.get("result", {
            "success": False,
            "error": "No result returned from server"
        })
        
    except requests.exceptions.ConnectionError:
        # Handle the case where the server is not running
        return {
            "success": False,
            "error": f"Cannot connect to MCP server at {MCP_URL}. "
                    "Make sure the server is running with 'agentic-docker server'."
        }
        
    except requests.exceptions.Timeout:
        # Handle the case where the request times out
        return {
            "success": False,
            "error": f"Request to MCP server timed out after 30 seconds"
        }
        
    except requests.exceptions.RequestException as e:
        # Handle other request-related errors (network issues, etc.)
        return {
            "success": False,
            "error": f"Network error occurred: {str(e)}"
        }
        
    except json.JSONDecodeError:
        # Handle the case where the server response is not valid JSON
        return {
            "success": False,
            "error": f"Server returned invalid JSON response: {response.text}"
        }
        
    except Exception as e:
        # Handle any other unexpected errors
        return {
            "success": False,
            "error": f"Unexpected error occurred: {str(e)}"
        }

def test_connection() -> bool:
    """
    Test if the MCP server is accessible.
    
    This function attempts to make a simple request to verify that
    the server is running and responding correctly.
    
    Returns:
        bool: True if the server is accessible, False otherwise
    """
    try:
        # Make a simple request to test connectivity
        # We'll call the list containers tool with default parameters
        response = call_tool("docker_list_containers", {})
        
        # If we get a response (even if it's an error), the server is accessible
        return True
    except Exception:
        # If any exception occurs, the server is not accessible
        return False

def get_available_tools() -> Optional[list]:
    """
    Get the list of available tools from the server.
    
    Note: This is a placeholder for future implementation. Currently,
    the tool list is managed by the tools registry, not the server.
    In a real MCP implementation, there would be a method to introspect
    available tools.
    
    Returns:
        Optional[list]: List of available tool names (or None if not implemented)
    """
    # For now, we don't have a server endpoint to list tools
    # This would be implemented in a full MCP server as a discovery endpoint
    # For our implementation, the tools list is in the tools registry
    return None

def call_k8s_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a JSON-RPC request to the Kubernetes MCP server to execute a specific K8s tool.
    
    This function is similar to call_tool but routes to the K8s MCP server.
    
    Args:
        tool_name (str): The name of the K8s tool to execute (e.g., "k8s_list_pods")
        arguments (Dict[str, Any]): The parameters to pass to the tool
        
    Returns:
        Dict[str, Any]: The result from the tool execution
    """
    payload = {
        "jsonrpc": "2.0",
        "method": tool_name,
        "params": arguments,
        "id": 1
    }
    
    try:
        response = requests.post(
            url=K8S_MCP_URL,
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            return {
                "success": False,
                "error": result["error"],
                "original_response": result
            }
        
        return result.get("result", {
            "success": False,
            "error": "No result returned from K8s server"
        })
        
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to K8s MCP server at {K8S_MCP_URL}. "
                    "Make sure the server is running with 'agentic-docker k8s-server'."
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": f"Request to K8s MCP server timed out after 30 seconds"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Network error occurred: {str(e)}"
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"K8s server returned invalid JSON response: {response.text}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error occurred: {str(e)}"
        }

def test_k8s_connection() -> bool:
    """
    Test if the Kubernetes MCP server is accessible.
    
    Returns:
        bool: True if the K8s server is accessible, False otherwise
    """
    try:
        response = call_k8s_tool("k8s_list_pods", {"namespace": "default"})
        return True
    except Exception:
        return False

def call_remote_k8s_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a JSON-RPC request to the Remote Kubernetes MCP server.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": tool_name,
        "params": arguments,
        "id": 1
    }
    
    try:
        response = requests.post(
            url=REMOTE_K8S_MCP_URL,
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            return {
                "success": False,
                "error": result["error"],
                "original_response": result
            }
        
        return result.get("result", {
            "success": False,
            "error": "No result returned from Remote K8s server"
        })
        
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to Remote K8s MCP server at {REMOTE_K8S_MCP_URL}. "
                    "Make sure the server is running."
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": f"Request to Remote K8s MCP server timed out after 30 seconds"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Network error occurred: {str(e)}"
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Remote K8s server returned invalid JSON response: {response.text}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error occurred: {str(e)}"
        }

def test_remote_k8s_connection() -> bool:
    """
    Test if the Remote Kubernetes MCP server is accessible.
    """
    try:
        response = call_remote_k8s_tool("remote_k8s_list_pods", {"namespace": "default"})
        return True
    except Exception:
        return False

# Example of what a JSON-RPC request looks like:
"""
{
    "jsonrpc": "2.0",
    "method": "docker_run_container",
    "params": {
        "image": "nginx",
        "ports": {"8080": "80"}
    },
    "id": 1
}
"""

# Example of what a JSON-RPC response looks like:
"""
{
    "jsonrpc": "2.0",
    "result": {
        "success": true,
        "container_id": "abc123",
        "name": "angry_bell",
        "message": "Container angry_bell started successfully with image nginx."
    },
    "id": 1
}
"""