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

def get_tool_calls(user_query: str, tools_schema: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ask the LLM to choose one or more tools and parameters based on the user's natural language query.
    
    This function constructs a prompt that includes the available tools schema
    and asks the LLM to return a list of structured tool calls in JSON format.
    It supports command chaining by allowing the LLM to return multiple tool calls
    for a single query (e.g., "Start nginx and list pods").
    
    Args:
        user_query (str): The user's natural language request
        tools_schema (List[Dict[str, Any]]): List of available tools with their schemas
        
    Returns:
        List[Dict[str, Any]]: A list of tool calls, where each call is {"name": "...", "arguments": {...}}
                              Returns empty list if parsing fails or no suitable tool found
    """
    # Convert the tools schema to a nicely formatted JSON string for the prompt
    tools_json = json.dumps(tools_schema, indent=2)
    
    # Construct the system prompt that guides the LLM's behavior
    prompt = f"""
You are a Docker assistant. The user wants to perform one or more Docker/Kubernetes operations.
Your job is to choose the most appropriate tool(s) from the available tools below.

Available tools (in JSON Schema format):
{tools_json}

INSTRUCTIONS:
1. Only use tools from the list above.
2. You MUST return a JSON LIST of tool calls, even if there is only one tool.
3. Do NOT add tools that were not explicitly requested by the user.
4. Respond ONLY with a valid JSON LIST in this format:
   [
     {{"name": "tool_name", "arguments": {{...}}}}
   ]
   OR for multiple tools:
   [
     {{"name": "first_tool", "arguments": {{...}}}},
     {{"name": "second_tool", "arguments": {{...}}}}
   ]
5. Do not include any other text or explanation.
6. Ensure the JSON is valid and follows the schema requirements.
7. If the request is unclear or doesn't match any tool, return an empty JSON list [].

User request: "{user_query}"
"""
    
    try:
        # Send the prompt to the Ollama model
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,  # Low temperature for consistency
                "top_p": 0.9,
                "num_predict": 500    # Increased token limit for multiple tools
            }
        )
        
        # Extract the content from the response
        content = response['message']['content'].strip()
        
        # Handle cases where the LLM wraps the JSON in markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
            content = content[:content.rfind("```")]
            content = content.strip()
        elif content.startswith("```"):
            content = content[3:]
            content = content[:content.rfind("```")]
            content = content.strip()
        
        # Parse the JSON content
        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: Try to use raw_decode if there's extra text
            decoder = json.JSONDecoder()
            parsed_content, _ = decoder.raw_decode(content)
            
        # Normalize the output to a list of tool calls
        tool_calls = []
        
        if isinstance(parsed_content, list):
            # If it's already a list, use it directly
            tool_calls = parsed_content
        elif isinstance(parsed_content, dict):
            # If it's a single object, wrap it in a list (backward compatibility)
            tool_calls = [parsed_content]
        else:
            print(f"⚠️  LLM returned invalid JSON structure (not list or dict): {type(parsed_content)}")
            return []
            
        # Validate each tool call in the list
        valid_tool_calls = []
        for call in tool_calls:
            if isinstance(call, dict) and "name" in call:
                # Ensure arguments key exists
                if "arguments" not in call:
                    call["arguments"] = {}
                
                # Validate arguments is a dict
                if isinstance(call["arguments"], dict):
                    valid_tool_calls.append(call)
                else:
                    print(f"⚠️  Skipping invalid tool call (arguments not dict): {call}")
            else:
                print(f"⚠️  Skipping invalid tool call structure: {call}")
                
        return valid_tool_calls
            
    except json.JSONDecodeError as e:
        print(f"⚠️  LLM response is not valid JSON: {e}")
        print(f"   Raw response: {content[:200]}...")
        return []
        
    except Exception as e:
        print(f"⚠️  Error communicating with LLM: {e}")
        return []

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