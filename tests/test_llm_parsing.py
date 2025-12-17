import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import builtins
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from devops_agent.llm.ollama_client import get_tool_call

class TestLLMParsing(unittest.TestCase):

    def setUp(self):
        # Mock print to avoid Unicode errors on Windows
        self.print_patcher = patch('builtins.print')
        self.mock_print = self.print_patcher.start()

    def tearDown(self):
        self.print_patcher.stop()

    @patch('devops_agent.llm.ollama_client.ollama.chat')
    def test_missing_arguments_key(self, mock_chat):
        # Simulate LLM response without arguments key
        mock_response = {
            'message': {
                'content': '{"name": "k8s_list_nodes"}'
            }
        }
        mock_chat.return_value = mock_response
        
        # Call get_tool_call
        result = get_tool_call("List nodes", [])
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], "k8s_list_nodes")
        self.assertEqual(result['arguments'], {})

    @patch('devops_agent.llm.ollama_client.ollama.chat')
    def test_valid_response(self, mock_chat):
        # Simulate valid LLM response
        mock_response = {
            'message': {
                'content': '{"name": "docker_run", "arguments": {"image": "nginx"}}'
            }
        }
        mock_chat.return_value = mock_response
        
        # Call get_tool_call
        result = get_tool_call("Run nginx", [])
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], "docker_run")
        self.assertEqual(result['arguments'], {'image': 'nginx'})

if __name__ == '__main__':
    unittest.main()
