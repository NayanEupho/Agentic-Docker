# devops_agent/llm/ollama_client.py
"""
Ollama LLM Client

This client communicates with local or remote Ollama models to interpret natural language
queries and convert them into structured tool calls. It handles prompting,
response parsing, and ensures the LLM returns valid JSON for tool execution.
"""

# Import the Ollama library for local LLM communication
import ollama
# Import JSON library for handling JSON data
import json
# Import typing utilities for type hints
from typing import Optional, Dict, List, Any

# Configuration
from ..settings import settings
MODEL = settings.LLM_MODEL

def get_client(host: str = None) -> ollama.Client:
    """Get an Ollama client instance pointing to the configured host."""
    # Use provided host or fall back to settings
    ollama_host = host if host else settings.LLM_HOST
    return ollama.Client(host=ollama_host)

def get_tool_calls(
    user_query: str, 
    tools_schema: List[Dict[str, Any]], 
    history: Optional[List[Dict[str, str]]] = None
) -> List[Dict[str, Any]]:
    """
    Ask the LLM to choose one or more tools and parameters based on the user's natural language query.
    """
    # Convert the tools schema to a nicely formatted JSON string for the prompt
    tools_json = json.dumps(tools_schema, indent=2)
    
    # Construct the system instruction that guides the LLM's behavior
    system_instructions = f"""
You are a Docker assistant. The user wants to perform one or more Docker/Kubernetes operations.
Your job is to choose the most appropriate tool(s) from the available tools below.

Available tools (in JSON Schema format):
{tools_json}

INSTRUCTIONS:
1. Only use tools from the list above.
2. You MUST return a JSON LIST of tool calls.
3. If the user is just chatting or asking a question that doesn't need a specific Docker/K8s action, use the `chat` tool.
4. Respond ONLY with a valid JSON LIST in this format:
   [
     {{"name": "tool_name", "arguments": {{"arg1": "value1", ...}}}}
   ]
5. Do not include any other text or explanation.
6. Ensure the JSON is valid and follows the schema requirements.
7. If the request is truly invalid and even `chat` is not appropriate, return [].

CRITICAL - FORMATTING:
- The output MUST be a strict JSON list.
- Each item MUST have "name" and "arguments" keys.
- "arguments" MUST be a dictionary/object, even if empty (e.g., "arguments": {{}}).
- Do NOT output `{{ "name": "foo", {{}} }}` (missing "arguments" key).
- WRONG: [ {{"name": "docker_list_containers", {{"all": true}}}} ]
- RIGHT: [ {{"name": "docker_list_containers", "arguments": {{"all": true}}}} ]

CRITICAL - ARGUMENTS:
- ALWAYS include ALL required arguments in the "arguments" object.
- If the user says "first node" or "1st", look in the conversation history for node names and use the FIRST one (e.g., "kc-m1").
- If the user says "second node" or "2nd", use the SECOND node name from history (e.g., "kc-w1").
- NEVER leave required arguments empty. Infer values from context.

IMPORTANT REGARDING HISTORY:
- The conversation history shows outputs of previous tool executions.
- Do NOT repeat previous actions unless explicitly asked again.
- PRIORITIZE the "CURRENT QUERY".
- Use history ONLY to resolve references (e.g., "describe [that] node", "IP of [it]").
- If the current query is unrelated to history (e.g., "List pods" after "Describe node"), IGNORE previous node context and run the new command.
"""
    
    # Prepare messages list
    final_messages = [{"role": "system", "content": system_instructions}]
    
    # Add History (if any)
    if history:
        final_messages.extend(history)
        
    # Add Current User Query
    final_messages.append({
        "role": "user", 
        "content": f"--- CURRENT QUERY ---\n{user_query}\n\n(Ignore previous specific commands. Focus on THIS query. Use history ONLY for context/references like 'that', 'it', '1st'.)"
    })

    try:
        import time
        start_time = time.time()
        
        # Use dynamic client
        client = get_client()
        
        response = client.chat(
            model=MODEL,
            messages=final_messages,
            options={
                "temperature": settings.LLM_TEMPERATURE,
                "top_p": 0.9,
                "num_predict": 500
            }
        )
        duration = time.time() - start_time
        print(f"DEBUG: LLM Inference took {duration:.2f} seconds")
        
        # Extract the content from the response
        content = response['message']['content'].strip()
        print(f"DEBUG: Raw LLM Response: {content}")
        
        # Write to debug file
        try:
            with open("llm_debug.log", "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

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
        parsed_content = None
        try:
            # First try direct parse
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            # Fallback 1: Try to find a JSON list pattern in the text
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    parsed_content = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            
            if parsed_content is None:
               # Fallback 2: Try to find a single JSON object pattern "{...}"
               match_obj = re.search(r'\{.*\}', content, re.DOTALL)
               if match_obj:
                   try:
                       parsed_content = json.loads(match_obj.group(0))
                   except json.JSONDecodeError:
                       pass

            # If still None, maybe use raw_decode as last resort
            if parsed_content is None:
                 try:
                    decoder = json.JSONDecoder()
                    parsed_content, _ = decoder.raw_decode(content)
                 except Exception:
                    pass
            
            # Fallback 3: Try to repair truncated JSON (common with local LLM token limits)
            if parsed_content is None:
                try:
                    # Check if it looks like an unclosed list
                    if content.strip().startswith("[") and not content.strip().endswith("]"):
                        # Try appending closing bracket
                        print("⚠️  Attempting to repair truncated JSON response...")
                        repaired_content = content + "]"
                        parsed_content = json.loads(repaired_content)
                except json.JSONDecodeError:
                    # Try appending object closure too "}]" if it ended inside an object
                    try:
                        repaired_content = content + "}]"
                        parsed_content = json.loads(repaired_content)
                    except Exception:
                        pass
            
            # Fallback 4: "Inject" missing arguments key
            if parsed_content is None:
                import re
                params_pattern = r'("name":\s*"[^"]+")\s*,\s*(\{)'
                if re.search(params_pattern, content):
                    print("⚠️  Injecting missing 'arguments' key into JSON response...")
                    fixed_content = re.sub(params_pattern, r'\1, "arguments": \2', content)
                    try:
                        parsed_content = json.loads(fixed_content)
                    except json.JSONDecodeError:
                         if fixed_content.strip().startswith("[") and not fixed_content.strip().endswith("]"):
                             try:
                                 parsed_content = json.loads(fixed_content + "]")
                             except Exception:
                                 pass
        
        # Normalize the output to a list of tool calls
        tool_calls = []
        
        if isinstance(parsed_content, list):
            tool_calls = parsed_content
        elif isinstance(parsed_content, dict):
            tool_calls = [parsed_content]
        else:
            print(f"⚠️  LLM returned invalid JSON structure (not list or dict): {type(parsed_content)}")
            return []
            
        # Validate each tool call in the list
        valid_tool_calls = []
        for call in tool_calls:
            if isinstance(call, dict) and "name" in call:
                if "arguments" not in call:
                    call["arguments"] = {}
                
                if isinstance(call["arguments"], dict):
                    valid_tool_calls.append(call)
                else:
                    print(f"⚠️  Skipping invalid tool call (arguments not dict): {call}")
            else:
                print(f"⚠️  Skipping invalid tool call structure: {call}")
                
        return valid_tool_calls
            
    except json.JSONDecodeError as e:
        print(f"⚠️  LLM response is not valid JSON: {e}")
        return []
        
    except Exception as e:
        print(f"⚠️  Error communicating with LLM: {e}")
        return []

def test_llm_connection() -> bool:
    """
    Test if the LLM is accessible and responding correctly.
    """
    try:
        client = get_client()
        # Send a simple test query
        response = client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": "Hello, are you working?"}],
            options={"temperature": 0.1}
        )
        
        if response and 'message' in response:
            return True
        return False
        
    except Exception:
        return False

def list_available_models(host: str = None) -> List[str]:
    """
    Get a list of available models from Ollama (local or remote).
    
    Args:
        host (str): Optional host override to fetch models from a specific server.
    """
    try:
        # Use dynamic client
        client = get_client(host=host)
        
        response = client.list()
        
        # Handle object-based response (newer ollama lib)
        if hasattr(response, 'models'):
            models_data = response.models
        elif isinstance(response, dict):
            models_data = response.get('models', [])
        else:
            models_data = response if isinstance(response, list) else []
            
        models = []
        for model in models_data:
            if hasattr(model, 'model'):
                models.append(model.model)
            elif isinstance(model, dict):
                name = model.get('name') or model.get('model')
                if name:
                    models.append(name)
                    
        return models
    except Exception as e:
        print(f"⚠️  Error listing Ollama models: {e}")
        return []

def ensure_model_exists(force_test: bool = False) -> bool:
    """
    Check if the configured model exists, and pull it if it doesn't.
    """
    if not force_test:
        return True

    try:
        available_models = list_available_models()
        model_exists = any(m == MODEL or m.startswith(f"{MODEL}:") for m in available_models)
        
        if model_exists:
             print(f"✅ Model '{MODEL}' found in list at {settings.LLM_HOST}.")
             pass
    except Exception as list_error:
        print(f"⚠️  Could not list models: {list_error}")

    print(f"🔍 Testing direct access to model '{MODEL}' at {settings.LLM_HOST}...")
    try:
        client = get_client()
        response = client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": "test"}],
            options={"temperature": 0.1, "num_predict": 5}
        )
        print(f"✅ Model '{MODEL}' is accessible and working.")
        return True 
    except Exception as direct_test_error:
        print(f"⚠️  Direct test for model '{MODEL}' failed: {direct_test_error}")

    print(f"📦 Model '{MODEL}' not found or not working. Attempting to pull from Ollama...")
    
    try:
        client = get_client()
        client.pull(MODEL)
        print(f"✅ Model '{MODEL}' pulled successfully!")
        return True
    except Exception as pull_error:
        print(f"❌ Failed to pull model '{MODEL}': {pull_error}")
        return False

