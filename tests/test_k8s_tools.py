import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path so we can import agentic_docker
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agentic_docker.k8s_tools.k8s_list_pods import K8sListPodsTool
from agentic_docker.k8s_tools.k8s_list_nodes import K8sListNodesTool

class TestK8sTools(unittest.TestCase):

    @patch('requests.get')
    def test_list_pods_success(self, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "pod-1", "namespace": "default"},
                    "status": {
                        "phase": "Running",
                        "podIP": "10.0.0.1",
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "containerStatuses": [{"ready": True}]
                    },
                    "spec": {
                        "nodeName": "node-1",
                        "containers": [{}]
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        # Run tool
        tool = K8sListPodsTool()
        result = tool.run(namespace="default")

        # Verify
        self.assertTrue(result['success'])
        self.assertEqual(len(result['pods']), 1)
        self.assertEqual(result['pods'][0]['name'], "pod-1")
        self.assertEqual(result['pods'][0]['phase'], "Running")
        
        # Verify API call
        mock_get.assert_called_with("http://127.0.0.1:8001/api/v1/namespaces/default/pods", timeout=10)

    @patch('requests.get')
    def test_list_nodes_success(self, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {
                        "name": "node-1",
                        "labels": {"node-role.kubernetes.io/worker": ""}
                    },
                    "status": {
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "addresses": [{"type": "InternalIP", "address": "192.168.1.1"}],
                        "capacity": {"cpu": "4", "memory": "16Gi"},
                        "nodeInfo": {"kubeletVersion": "v1.29.0", "osImage": "Linux"}
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        # Run tool
        tool = K8sListNodesTool()
        result = tool.run()

        # Verify
        self.assertTrue(result['success'])
        self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['nodes'][0]['name'], "node-1")
        self.assertEqual(result['nodes'][0]['status'], "Ready")
        self.assertIn("worker", result['nodes'][0]['roles'])
        
        # Verify API call
        mock_get.assert_called_with("http://127.0.0.1:8001/api/v1/nodes", timeout=10)

if __name__ == '__main__':
    unittest.main()
