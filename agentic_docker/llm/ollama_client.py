# agentic_docker/llm/ollama_client.py
"""
Ollama LLM Client

This client communicates with local Ollama models to interpret natural language
queries and convert them into structured tool calls. It handles prompting,
response parsing, and ensures the LLM returns valid JSON for tool execution.
"""

# Import the Ollama library for local LLM communication
import ollama
# Import JSON library for handling JSON data
import json
# Import typing utilities for type hints
from typing import Optional, Dict, List, Any

# Configuration: The model to use for processing queries
# This should be a model available in Ollama (install with 'ollama pull <model>')
MODEL = "phi3:mini"  # Fast, small model (~3.8GB) that runs well on CPU
# Alternative models you could use:
# MODEL = "llama3:8b"  # Larger, more capable model (~5GB)
# MODEL = "mistral:7b"  # Another good option (~4GB)

def get_tool_call(user_query: str, tools_schema: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Ask the LLM to choose a tool and parameters based on the user's natural language query.
    
    This function constructs a prompt that includes the available tools schema
    and asks the LLM to return a structured tool call in JSON format.
    
    Args:
        user_query (str): The user's natural language request (e.g., "Start nginx on port 8080")
        tools_schema (List[Dict[str, Any]]): List of available tools with their schemas
        
    Returns:
        Optional[Dict[str, Any]]: The tool call in format {"name": "...", "arguments": {...}}
                                 Returns None if parsing fails or no suitable tool found
    """
    # Convert the tools schema to a nicely formatted JSON string for the prompt
    # This helps the LLM understand what tools are available and how to use them
    tools_json = json.dumps(tools_schema, indent=2)
    
    # Construct the system prompt that guides the LLM's behavior
    # This prompt teaches the LLM:
    # 1. What its role is (Docker assistant)
    # 2. What tools are available
    # 3. How to format its response (valid JSON only)
    prompt = f"""
You are a Docker assistant. The user wants to perform a Docker operation.
Your job is to choose the most appropriate tool from the available tools below.

Available tools (in JSON Schema format):
{tools_json}

INSTRUCTIONS:
1. Only use tools from the list above
2. Respond ONLY with a valid JSON object in this exact format:
   {{"name": "tool_name", "arguments": {{...}}}}
3. Do not include any other text or explanation
4. Ensure the JSON is valid and follows the schema requirements
5. If the request is unclear or doesn't match any tool, return an empty JSON object

User request: "{user_query}"
"""
    
    try:
        # Send the prompt to the Ollama model
        # Use a low temperature for more deterministic responses
        response = ollama.chat(
            model=MODEL,  # Which model to use
            messages=[    # Conversation history (just the user's message for this simple case)
                {"role": "user", "content": prompt}
            ],
            options={     # Model-specific options
                "temperature": 0.1,  # Low temperature = more consistent, deterministic output
                "top_p": 0.9,        # Controls randomness in token selection
                "num_predict": 200    # Maximum number of tokens to generate
            }
        )
        
        # Extract the content from the response
        content = response['message']['content'].strip()
        
        # Handle cases where the LLM wraps the JSON in markdown code blocks
        # This is common when models are trained on code/documentation
        if content.startswith("```json"):
            # Remove the ```json and closing ``` markers
            content = content[7:]  # Remove starting ```json
            content = content[:content.rfind("```")]  # Remove ending ```
            content = content.strip()  # Remove any extra whitespace
        
        # NEW: Use json.JSONDecoder.raw_decode to parse the FIRST valid JSON object
        # This method parses the JSON from the beginning of the string and returns
        # the parsed object along with the index where parsing stopped.
        # This handles cases where the LLM appends extra text after the JSON.
        decoder = json.JSONDecoder()
        # raw_decode returns (parsed_object, index_where_parsing_stopped)
        tool_call, end_idx = decoder.raw_decode(content)
        
        # Validate that the response has the required structure
        if "name" in tool_call:
            # Ensure arguments key exists, default to empty dict if missing
            if "arguments" not in tool_call:
                tool_call["arguments"] = {}
            
            # Additional validation: ensure arguments is a dictionary
            if isinstance(tool_call["arguments"], dict):
                return tool_call
            else:
                print(f"⚠️  LLM returned invalid arguments type: {type(tool_call['arguments'])}")
                return None
        else:
            print(f"⚠️  LLM returned invalid JSON structure: {tool_call}")
            return None
            
    except json.JSONDecodeError as e:
        # Handle cases where the LLM response does not start with valid JSON
        print(f"⚠️  LLM response does not start with valid JSON: {e}")
        print(f"   Raw response (after markdown processing): {content[:200]}...")
        return None
        
    except KeyError as e:
        # Handle cases where expected keys are missing from the response
        print(f"⚠️  Missing key in LLM response: {e}")
        return None
        
    except Exception as e:
        # Handle any other unexpected errors during LLM communication
        print(f"⚠️  Error communicating with LLM: {e}")
        return None

def test_llm_connection() -> bool:
    """
    Test if the LLM is accessible and responding correctly.
    
    This function sends a simple test query to verify that Ollama is running
    and the specified model is available.
    
    Returns:
        bool: True if the LLM is accessible and responding, False otherwise
    """
    try:
        # Send a simple test query
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": "Hello, are you working?"}],
            options={"temperature": 0.1}
        )
        
        # Check if we got a response
        if response and 'message' in response:
            return True
        return False
        
    except Exception:
        # If any error occurs, the LLM is not accessible
        return False

def list_available_models() -> List[str]:
    """
    Get a list of available models from Ollama.
    
    This function queries Ollama to see what models are currently installed
    and available for use. Handles proxy issues and unexpected response structures.
    
    Returns:
        List[str]: List of available model names, or empty list if listing fails
    """
    try:
        response = ollama.list()
        # The response structure might be different than expected.
        # It could be {'models': [...]} or just [...].
        # Try to get the models list safely.
        models_data = response.get('models', response if isinstance(response, list) else [])
        # Extract model names from the response, assuming each model dict has a 'name' key
        models = [model.get('name') for model in models_data if isinstance(model, dict) and 'name' in model]
        # Filter out any None values that might result from missing 'name' keys
        models = [name for name in models if name is not None]
        return models
    except Exception as e:
        # If listing fails (e.g., due to proxy or unexpected format), return empty list
        print(f"⚠️  Error listing Ollama models: {e}")
        return []

def ensure_model_exists() -> bool:
    """
    Check if the configured model exists, and pull it if it doesn't.
    
    This function ensures that the required model is available in Ollama.
    It bypasses registry calls that might be blocked by corporate proxies
    by first attempting to use the model directly.
    
    Returns:
        bool: True if the model exists and is accessible, False otherwise
    """
    # First, try to get the list of models (but this might fail behind proxy or due to format)
    try:
        available_models = list_available_models()
        if MODEL in available_models:
            print(f"✅ Model '{MODEL}' found in local list.")
            # If model is listed, try to run a simple test to confirm it works
            try:
                ollama.chat(
                    model=MODEL,
                    messages=[{"role": "user", "content": "test"}],
                    options={"temperature": 0.1, "num_predict": 5} # Limit response length for test
                )
                print(f"✅ Model '{MODEL}' is accessible and working.")
                return True  # Model exists and is working
            except Exception as test_error:
                print(f"⚠️  Model '{MODEL}' found locally but test failed: {test_error}")
                # Fall through to pull attempt
    except Exception as list_error:
        print(f"⚠️  Could not list models or check if '{MODEL}' exists locally: {list_error}")
        # If listing fails, proceed to direct test and then pull

    # If listing failed or model wasn't found/listed, try to run a simple test with the *configured* MODEL directly.
    # This might work even if ollama.list() doesn't, if the model exists but isn't listed correctly or the list call is blocked.
    print(f"🔍 Testing direct access to model '{MODEL}'...")
    try:
        # Test if the model can be used without pulling
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": "test"}],
            options={"temperature": 0.1, "num_predict": 5} # Limit response length for test
        )
        print(f"✅ Model '{MODEL}' is accessible and working (confirmed by direct test).")
        return True  # Model exists and is working
    except Exception as direct_test_error:
        print(f"⚠️  Direct test for model '{MODEL}' failed: {direct_test_error}")

    print(f"📦 Model '{MODEL}' not found or not working. Attempting to pull from Ollama...")
    
    try:
        # Pull the model from Ollama
        ollama.pull(MODEL)
        print(f"✅ Model '{MODEL}' pulled successfully!")
        return True
    except Exception as pull_error:
        print(f"❌ Failed to pull model '{MODEL}': {pull_error}")
        print(f"   Make sure Ollama is running and the model name is correct.")
        print(f"   You can manually install it with: ollama pull {MODEL}")
        return False

# Example of what the LLM should return:
"""
{
    "name": "docker_run_container",
    "arguments": {
        "image": "nginx",
        "ports": {"8080": "80"}
    }
}
"""