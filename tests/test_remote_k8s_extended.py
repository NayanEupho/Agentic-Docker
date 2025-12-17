import unittest
from unittest.mock import MagicMock, patch
import json
from devops_agent.k8s_tools.remote_k8s_extended_tools import (
    RemoteK8sListDeploymentsTool,
    RemoteK8sDescribeDeploymentTool,
    RemoteK8sListNamespacesTool,
    RemoteK8sFindPodNamespaceTool,
    RemoteK8sGetResourcesIPsTool
)
from devops_agent.k8s_tools.k8s_config import k8s_config

class TestRemoteK8sExtendedTools(unittest.TestCase):

    def setUp(self):
        # Configure dummy remote settings
        k8s_config.configure_remote("https://mock-k8s:6443", "mock-token")

    @patch('requests.get')
    def test_list_namespaces(self, mock_get):
        # Mock API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "default", "creationTimestamp": "2023-01-01T00:00:00Z"},
                    "status": {"phase": "Active"}
                },
                {
                    "metadata": {"name": "kube-system", "creationTimestamp": "2023-01-01T00:00:00Z"},
                    "status": {"phase": "Active"}
                }
            ]
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        tool = RemoteK8sListNamespacesTool()
        result = tool.run()

        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['namespaces'][0]['name'], 'default')
        self.assertEqual(result['namespaces'][1]['name'], 'kube-system')

    @patch('requests.get')
    def test_find_pod_namespace(self, mock_get):
        # Mock API response for listing all pods
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "nginx-pod", "namespace": "default"}
                },
                {
                    "metadata": {"name": "coredns", "namespace": "kube-system"}
                }
            ]
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        tool = RemoteK8sFindPodNamespaceTool()
        result = tool.run(pod_names=["nginx-pod", "missing-pod"])

        self.assertTrue(result['success'])
        self.assertEqual(result['pod_locations']['nginx-pod'], ['default'])
        self.assertEqual(result['pod_locations']['missing-pod'], 'Not Found')

    @patch('requests.get')
    def test_get_pod_ips(self, mock_get):
        # Mock API response for pods
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "nginx-pod", "namespace": "default"},
                    "status": {"podIP": "10.1.1.1", "hostIP": "192.168.1.100"},
                    "spec": {
                        "containers": [
                            {"ports": [{"containerPort": 80, "protocol": "TCP"}]}
                        ]
                    }
                }
            ]
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        tool = RemoteK8sGetResourcesIPsTool()
        result = tool.run(resource_type="pod", names=["nginx-pod"])

        self.assertTrue(result['success'])
        self.assertEqual(result['ips']['nginx-pod']['pod_ip'], "10.1.1.1")
        self.assertEqual(result['ips']['nginx-pod']['ports'], ["80/TCP"])

    @patch('requests.get')
    def test_get_node_ips(self, mock_get):
        # Mock API response for nodes
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "worker-node-1"},
                    "status": {
                        "addresses": [
                            {"type": "InternalIP", "address": "192.168.1.101"},
                            {"type": "Hostname", "address": "worker-node-1"}
                        ]
                    }
                }
            ]
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        tool = RemoteK8sGetResourcesIPsTool()
        result = tool.run(resource_type="node", names=["worker-node-1"])

        self.assertTrue(result['success'])
        self.assertEqual(result['ips']['worker-node-1']['InternalIP'], "192.168.1.101")

if __name__ == '__main__':
    unittest.main()
