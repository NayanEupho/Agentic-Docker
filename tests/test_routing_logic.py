
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# Mock the dependencies
sys.modules["agentic_docker.llm.ollama_client"] = MagicMock()
sys.modules["agentic_docker.mcp.client"] = MagicMock()
sys.modules["agentic_docker.safety"] = MagicMock()
sys.modules["agentic_docker.tools"] = MagicMock()
sys.modules["agentic_docker.k8s_tools"] = MagicMock()
sys.modules["agentic_docker.k8s_tools.remote_k8s_tools"] = MagicMock()

from agentic_docker.agent import process_query
from agentic_docker.llm.ollama_client import get_tool_call
from agentic_docker.mcp.client import call_tool, call_k8s_tool, call_remote_k8s_tool
from agentic_docker.safety import confirm_action_auto

# Setup mocks
confirm_action_auto.return_value = True

def test_docker_routing():
    print("Testing Docker routing...")
    get_tool_call.return_value = {"name": "docker_list_containers", "arguments": {}}
    call_tool.return_value = {"success": True, "containers": [], "count": 0}
    
    process_query("list containers")
    
    call_tool.assert_called_once()
    call_k8s_tool.assert_not_called()
    call_remote_k8s_tool.assert_not_called()
    print("[PASS] Docker routing passed")

def test_local_k8s_routing():
    print("Testing Local K8s routing...")
    # Reset mocks
    call_tool.reset_mock()
    call_k8s_tool.reset_mock()
    call_remote_k8s_tool.reset_mock()
    
    get_tool_call.return_value = {"name": "k8s_list_pods", "arguments": {"namespace": "default"}}
    call_k8s_tool.return_value = {"success": True, "pods": [], "count": 0, "namespace": "default"}
    
    process_query("list local pods")
    
    call_tool.assert_not_called()
    call_k8s_tool.assert_called_once()
    call_remote_k8s_tool.assert_not_called()
    print("[PASS] Local K8s routing passed")

def test_remote_k8s_routing():
    print("Testing Remote K8s routing...")
    # Reset mocks
    call_tool.reset_mock()
    call_k8s_tool.reset_mock()
    call_remote_k8s_tool.reset_mock()
    
    get_tool_call.return_value = {"name": "remote_k8s_list_pods", "arguments": {"namespace": "default"}}
    call_remote_k8s_tool.return_value = {"success": True, "pods": [], "count": 0, "namespace": "default"}
    
    process_query("list remote pods")
    
    call_tool.assert_not_called()
    call_k8s_tool.assert_not_called()
    call_remote_k8s_tool.assert_called_once()
    print("[PASS] Remote K8s routing passed")

if __name__ == "__main__":
    try:
        test_docker_routing()
        test_local_k8s_routing()
        test_remote_k8s_routing()
        print("\n[SUCCESS] All routing tests passed!")
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
