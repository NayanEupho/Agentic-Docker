import dspy
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# =============================================
# Pydantic Models for Validation
# =============================================

class ToolCall(BaseModel):
    """Schema for a single tool call."""
    name: str = Field(description="The EXACT name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")

# =============================================
# DSPy Signature
# =============================================

class DockerAgentSignature(dspy.Signature):
    """
    You are an intelligent Docker and Kubernetes Assistant.
    Your goal is to map the user's natural language query to tool calls.
    
    Instructions:
    1. ANALYZE the 'history_context' and 'user_query'.
    2. THINK step-by-step about which tool matches the user's intent. 
    3. CHECK 'available_tools' to ensure the tool exists and arguments are correct.
    4. OUTPUT a "Thought" explaining your reasoning.
    5. OUTPUT the "tool_calls" as a JSON list.

    RICH CONTEXT:
    - If `System Context` is provided in the query, use it to resolve names (e.g. "restart web" -> "restart web-container-123").

    OUTPUT FORMAT:
    - Reasoning: [Your thought process]
    - tool_calls: [{"name": "tool_name", "arguments": {...}}]
    """
    
    history_context: str = dspy.InputField(desc="Previous conversation history")
    available_tools: str = dspy.InputField(desc="JSON schema of available tools")
    user_query: str = dspy.InputField(desc="The user's natural language command")
    
    tool_calls: str = dspy.OutputField(desc="JSON list of tool calls. Example: [{\"name\": \"k8s_list_pods\", \"arguments\": {}}]")

# =============================================
# DockerAgent Module with Retry
# =============================================

class FastDockerAgent(dspy.Module):
    """Zero-shot agent for high speed."""
    def __init__(self):
        super().__init__()
        self.prog = dspy.Predict(DockerAgentSignature)
    
    def forward(self, query: str, tools_schema: List[Dict], history: List[Dict]) -> dspy.Prediction:
        history_str = json.dumps(history, indent=2) if history else "[]"
        tools_str = json.dumps(tools_schema, indent=2)
        return self.prog(
            history_context=history_str,
            available_tools=tools_str,
            user_query=query
        )

class DockerAgent(dspy.Module):
    """
    Hybrid Agent:
    1. Tries Fast Zero-Shot approach first (Latency optimized).
    2. Falls back to CoT (Reasoning) if Fast fails validation (Reliability optimized).
    """
    def __init__(self, max_retries: int = 2):
        super().__init__()
        self.fast_agent = FastDockerAgent()
        self.smart_prog = dspy.ChainOfThought(DockerAgentSignature)
        self.max_retries = max_retries
    
    def forward(self, query: str, tools_schema: List[Dict], history: List[Dict]) -> dspy.Prediction:
        history_str = json.dumps(history, indent=2) if history else "[]"
        tools_str = json.dumps(tools_schema, indent=2)
        
        # --- ATTEMPT 1: FAST MODE (Zero-Shot) ---
        print("⚡ [FastAgent] Attempting zero-shot execution...")
        try:
            prediction = self.fast_agent(query=query, tools_schema=tools_schema, history=history)
            raw_output = prediction.tool_calls
            validated = _validate_and_parse(raw_output)
            
            if validated:
                is_valid_sem, sem_error = _validate_semantics(validated, tools_schema)
                if is_valid_sem:
                    prediction._validated_calls = validated
                    return prediction
                else:
                    print(f"⚠️ [FastAgent] Semantic Error: {sem_error}. Switching to CoT.")
            else:
                print("⚠️ [FastAgent] Invalid JSON. Switching to CoT.")
                
        except Exception as e:
            print(f"⚠️ [FastAgent] Error: {e}. Switching to CoT.")

        # --- ATTEMPT 2: SMART MODE (Chain-of-Thought with Retries) ---
        print("🧠 [SmartAgent] Switching to Chain-of-Thought reasoning...")
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Add error feedback to query if retrying
                modified_query = query
                if last_error and attempt > 0:
                    modified_query = f"{query}\n\n[SYSTEM: Your previous response was invalid. Error: {last_error}. Please output ONLY a valid JSON list.]"
                
                prediction = self.smart_prog(
                    history_context=history_str,
                    available_tools=tools_str,
                    user_query=modified_query
                )
                
                # Validate the output
                raw_output = prediction.tool_calls
                validated = _validate_and_parse(raw_output)
                
                if validated:
                    # --- SEMANTIC VERIFICATION ---
                    is_valid_sem, sem_error = _validate_semantics(validated, tools_schema)
                    if is_valid_sem:
                        # Return successful prediction
                        prediction._validated_calls = validated
                        return prediction
                    else:
                        last_error = f"Semantic Error: {sem_error}"
                        # print(f"⚠️  Agent Self-Correction Triggered: {last_error}")
                else:
                    last_error = "Output was not a valid JSON list of tool calls"
                    
            except Exception as e:
                last_error = str(e)
        
        # Return last prediction even if invalid (let caller handle)
        return prediction

def _validate_and_parse(output: str) -> Optional[List[Dict]]:
    """Validate and parse the output. Returns None if invalid."""
    import json_repair
    import re
    
    if not output or not isinstance(output, str):
        return None
    
    cleaned = output.strip()
    
    # Remove markdown code blocks
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1])
    
    # Try to extract JSON from prose if needed
    if not cleaned.startswith("[") and not cleaned.startswith("{"):
        # Look for embedded JSON
        json_match = re.search(r'\[\s*\{.*?\}\s*\]', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group()
        else:
            # Try single object
            json_match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = f"[{json_match.group()}]"
            else:
                return None
    
    try:
        data = json_repair.loads(cleaned)
        if isinstance(data, list) and len(data) > 0:
            # Validate structure
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    return _normalize_tool_list(data)
        elif isinstance(data, dict) and "name" in data:
            return [_normalize_single(data)]
    except:
        pass
    
    return None

def _normalize_single(item: Dict) -> Dict:
    """Normalize a single tool call dict."""
    args = item.get("arguments", item.get("parameters", {}))
    return {"name": item["name"], "arguments": args if args else {}}

def _normalize_tool_list(data: List) -> List[Dict[str, Any]]:
    """Normalize tool call list to standard format."""
    normalized = []
    
    # Handle [name, args] format
    if len(data) == 2 and isinstance(data[0], str) and isinstance(data[1], dict):
        return [{"name": data[0], "arguments": data[1]}]
    
    # Handle [name] format
    if len(data) == 1 and isinstance(data[0], str):
        return [{"name": data[0], "arguments": {}}]
    
    for item in data:
        if isinstance(item, str):
            normalized.append({"name": item, "arguments": {}})
        elif isinstance(item, dict) and "name" in item:
            normalized.append(_normalize_single(item))
    
    return normalized

def _validate_semantics(tool_calls: List[Dict], tools_schema: List[Dict]) -> tuple[bool, str]:
    """
    Check if tool names exist and required arguments are present.
    Returns (True, "") if valid, or (False, "Error message") if invalid.
    """
    # Create a map for fast lookup
    schema_map = {t['name']: t for t in tools_schema}
    
    for call in tool_calls:
        name = call.get('name')
        args = call.get('arguments', {})
        
        if name not in schema_map:
            # Suggestions?
            # primitive fuzzy match?
            return False, f"Tool '{name}' does not exist. Please check 'available_tools' for the correct name."
        
        schema = schema_map[name]
        params_schema = schema.get('parameters', {})
        required_params = params_schema.get('required', [])
        
        # Check required args
        if required_params:
            for req in required_params:
                if req not in args:
                    return False, f"Tool '{name}' is missing required argument: '{req}'."
                    
    return True, ""

# =============================================
# Public Parser Function
# =============================================

def parse_dspy_tool_calls(output: Any) -> List[Dict[str, Any]]:
    """
    Parse DSPy output into a list of tool call dicts.
    Handles various formats and edge cases.
    """
    import json_repair
    import re
    
    # Check for pre-validated calls (from retry mechanism)
    if hasattr(output, '_validated_calls'):
        return output._validated_calls
    
    # Handle string output
    if isinstance(output, str):
        result = _validate_and_parse(output)
        if result:
            return result
        
        # Last resort: try to find ANY tool name in the output
        # This handles prose responses that mention tool names
        cleaned = output.strip()
        
        # Look for tool names matching pattern 'remote_k8s_*' or similar
        tool_pattern = r'(remote_k8s_\w+|k8s_\w+|docker_\w+)'
        matches = re.findall(tool_pattern, cleaned)
        if matches:
            print(f"⚠️  Extracted tool name from prose: {matches[0]}")
            return [{"name": matches[0], "arguments": {}}]
        
        print(f"❌ Parse Error. Raw: {cleaned[:150]}...")
        return []
    
    print(f"❌ Unexpected output type: {type(output)}")
    return []
