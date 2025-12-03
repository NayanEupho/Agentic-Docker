import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import builtins

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agentic_docker.agent import process_query

class TestAgentRouting(unittest.TestCase):

    def setUp(self):
        # Mock print to avoid Unicode errors on Windows
        self.print_patcher = patch('builtins.print')
        self.mock_print = self.print_patcher.start()

    def tearDown(self):
        self.print_patcher.stop()

    @patch('agentic_docker.agent.ensure_model_exists')
    @patch('agentic_docker.agent.test_connection')
    @patch('agentic_docker.agent.test_k8s_connection')
    @patch('agentic_docker.agent.get_tool_call')
    @patch('agentic_docker.agent.confirm_action_auto')
    @patch('agentic_docker.agent.call_tool')
    @patch('agentic_docker.agent.call_k8s_tool')
    def test_route_to_k8s(self, mock_call_k8s, mock_call_docker, mock_confirm, mock_get_tool, mock_test_k8s, mock_test_docker, mock_model):
        # Setup mocks
        mock_model.return_value = True
        mock_test_docker.return_value = True
        mock_test_k8s.return_value = True
        mock_confirm.return_value = True
        
        # Simulate LLM choosing a K8s tool
        mock_get_tool.return_value = {
            "name": "k8s_list_pods",
            "arguments": {"namespace": "default"}
        }
        
        # Simulate successful execution
        mock_call_k8s.return_value = {
            "success": True,
            "pods": [],
            "count": 0,
            "namespace": "default"
        }

        # Run agent
        result = process_query("List pods")

        # Verify routing
        mock_call_k8s.assert_called_once()
        mock_call_docker.assert_not_called()
        self.assertIn("Success", result)

    @patch('agentic_docker.agent.ensure_model_exists')
    @patch('agentic_docker.agent.test_connection')
    @patch('agentic_docker.agent.test_k8s_connection')
    @patch('agentic_docker.agent.get_tool_call')
    @patch('agentic_docker.agent.confirm_action_auto')
    @patch('agentic_docker.agent.call_tool')
    @patch('agentic_docker.agent.call_k8s_tool')
    def test_route_to_docker(self, mock_call_k8s, mock_call_docker, mock_confirm, mock_get_tool, mock_test_k8s, mock_test_docker, mock_model):
        # Setup mocks
        mock_model.return_value = True
        mock_test_docker.return_value = True
        mock_test_k8s.return_value = True
        mock_confirm.return_value = True
        
        # Simulate LLM choosing a Docker tool
        mock_get_tool.return_value = {
            "name": "docker_list_containers",
            "arguments": {}
        }
        
        # Simulate successful execution
        mock_call_docker.return_value = {
            "success": True,
            "containers": [],
            "count": 0
        }

        # Run agent
        result = process_query("List containers")

        # Verify routing
        mock_call_docker.assert_called_once()
        mock_call_k8s.assert_not_called()
        self.assertIn("Success", result)

if __name__ == '__main__':
    unittest.main()
