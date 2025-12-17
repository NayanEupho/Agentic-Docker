import sys
import os
import time

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from devops_agent.llm.ollama_client import ensure_model_exists, get_client
from devops_agent.agent_module import ErrorAnalyzer
from devops_agent.agent import format_tool_result
from devops_agent.cli_helper import stream_echo

def test_streaming():
    print("\n--- TEST: Streaming Output ---")
    print("Streaming a sample sentence (watch timing)...")
    start = time.time()
    stream_echo("This text should appear character by character. 🏎️💨", speed=0.005)
    duration = time.time() - start
    print(f"(Took {duration:.2f}s)")

def test_dspy_error_analyzer():
    print("\n--- TEST: DSPy Error Analyzer ---")
    
    # 1. Setup
    print("Initializing Ollama/DSPy...")
    ensure_model_exists() # This sets up dspy.settings
    
    analyzer = ErrorAnalyzer()
    
    # 2. Mock Data
    user_query = "kubectl delete pod my-pod"
    error_summary = "Operation failed: 403 Forbidden"
    raw_error = {
        "kind": "Status",
        "apiVersion": "v1",
        "metadata": {},
        "status": "Failure",
        "message": "pods \"my-pod\" is forbidden: User \"system:serviceaccount:default:default\" cannot delete resource \"pods\" in API group \"\" in the namespace \"default\"",
        "reason": "Forbidden",
        "details": {
            "name": "my-pod",
            "kind": "pods"
        },
        "code": 403
    }
    
    # 3. Execution
    print("Invoking ErrorAnalyzer (this verifies LLM connectivity and DSPy signature)...")
    try:
        prediction = analyzer(
            user_query=user_query,
            error_summary=error_summary,
            raw_error=raw_error
        )
        print("\n✅ Analyzer Result:")
        print(f"Explanation Preview:\n{prediction.explanation}")
        
        # Validation
        if "What Happened" in prediction.explanation and "Possible Fixes" in prediction.explanation:
             print("\n✅ Structure Verified: Contains expected sections.")
        else:
             print("\n⚠️ Structure Warning: Output might not have standard sections.")
             
    except Exception as e:
        print(f"\n❌ ErrorAnalyzer Failed: {e}")
        import traceback
        traceback.print_exc()

def test_agent_formatting_integration():
    print("\n--- TEST: Agent Formatting Integration ---")
    
    # Mock result with raw_error
    mock_result = {
        "success": False,
        "error": "404 Not Found",
        "raw_error": {
            "code": 404,
            "message": "pod not found"
        }
    }
    
    print("Calling format_tool_result with raw_error (Should trigger AI explanation)...")
    try:
        # Note: This will make a real LLM call because format_tool_result instantiates ErrorAnalyzer
        output = format_tool_result("remote_k8s_describe_pod", mock_result)
        
        print("\n✅ Formatted Output:")
        print(output)
        
        if "🤖 **AI Explanation:**" in output:
            print("\n✅ Integration Verified: Output contains AI Explanation marker.")
        else:
             print("\n❌ Integration Failed: AI marker missing.")
             
    except Exception as e:
        print(f"\n❌ Formatting Failed: {e}")

if __name__ == "__main__":
    test_streaming()
    test_dspy_error_analyzer()
    test_agent_formatting_integration()
