import unittest
from unittest.mock import patch, MagicMock
from devops_agent.agent import process_query
from devops_agent.llm import ollama_client

class TestCommandChaining(unittest.TestCase):

    @patch('devops_agent.agent.get_tool_calls')
    @patch('devops_agent.agent.call_tool')
    @patch('devops_agent.agent.call_k8s_tool')
    @patch('devops_agent.agent.confirm_action_auto')
    def test_single_command_chaining(self, mock_confirm, mock_k8s_tool, mock_docker_tool, mock_get_tool_calls):
        """Test that a single command is executed correctly as a list of 1."""
        # Mock LLM returning a single tool call in a list
        mock_get_tool_calls.return_value = [{
            "name": "docker_list_containers",
            "arguments": {}
        }]
        mock_confirm.return_value = True
        
        # Mock tool execution result
        mock_docker_tool.return_value = {
            "success": True,
            "containers": [],
            "count": 0
        }
        
        result = process_query("list containers")
        
        # Verify get_tool_calls was called
        mock_get_tool_calls.assert_called_once()
        
        # Verify docker tool was called
        mock_docker_tool.assert_called_once_with("docker_list_containers", {})
        
        # Verify result contains success message
        self.assertIn("Success! No containers found", result)

    @patch('devops_agent.agent.get_tool_calls')
    @patch('devops_agent.agent.call_tool')
    @patch('devops_agent.agent.call_k8s_tool')
    @patch('devops_agent.agent.confirm_action_auto')
    def test_multi_command_chaining(self, mock_confirm, mock_k8s_tool, mock_docker_tool, mock_get_tool_calls):
        """Test that multiple commands are executed sequentially."""
        # Mock LLM returning two tool calls
        mock_get_tool_calls.return_value = [
            {
                "name": "docker_run_container",
                "arguments": {"image": "nginx"}
            },
            {
                "name": "k8s_list_pods",
                "arguments": {"namespace": "default"}
            }
        ]
        mock_confirm.return_value = True
        
        # Mock tool execution results
        mock_docker_tool.return_value = {
            "success": True,
            "container_id": "123",
            "name": "nginx-container",
            "message": "Container started"
        }
        mock_k8s_tool.return_value = {
            "success": True,
            "pods": [],
            "count": 0,
            "namespace": "default"
        }
        
        result = process_query("start nginx and list pods")
        
        # Verify get_tool_calls was called
        mock_get_tool_calls.assert_called_once()
        
        # Verify both tools were called
        mock_docker_tool.assert_called_once_with("docker_run_container", {"image": "nginx"})
        mock_k8s_tool.assert_called_once_with("k8s_list_pods", {"namespace": "default"})
        
        # Verify result contains output from both
        self.assertIn("Container started", result)
        self.assertIn("No pods found in namespace 'default'", result)

    @patch('devops_agent.llm.ollama_client.ollama.chat')
    def test_ollama_client_parsing_list(self, mock_chat):
        """Test that ollama_client correctly parses a JSON list response."""
        # Mock Ollama response with a JSON list
        mock_response = {
            'message': {
                'content': '[{"name": "tool1", "arguments": {}}, {"name": "tool2", "arguments": {}}]'
            }
        }
        mock_chat.return_value = mock_response
        
        tools = ollama_client.get_tool_calls("query", [])
        
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]['name'], 'tool1')
        self.assertEqual(tools[1]['name'], 'tool2')

    @patch('devops_agent.llm.ollama_client.ollama.chat')
    def test_ollama_client_parsing_single_object(self, mock_chat):
        """Test backward compatibility: parsing a single JSON object into a list."""
        # Mock Ollama response with a single JSON object
        mock_response = {
            'message': {
                'content': '{"name": "tool1", "arguments": {}}'
            }
        }
        mock_chat.return_value = mock_response
        
        tools = ollama_client.get_tool_calls("query", [])
        
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['name'], 'tool1')

if __name__ == '__main__':
    unittest.main()
