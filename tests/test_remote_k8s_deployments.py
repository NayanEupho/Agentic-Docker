import unittest
from unittest.mock import MagicMock, patch
import json
from devops_agent.k8s_tools.remote_k8s_extended_tools import (
    RemoteK8sListDeploymentsTool,
    RemoteK8sDescribeDeploymentTool
)
# Import the actual config object to patch it directly
from devops_agent.k8s_tools.k8s_config import k8s_config

class TestRemoteK8sDeploymentTools(unittest.TestCase):

    def setUp(self):
        self.list_tool = RemoteK8sListDeploymentsTool()
        self.describe_tool = RemoteK8sDescribeDeploymentTool()

    @patch('devops_agent.k8s_tools.remote_k8s_extended_tools.requests.get')
    def test_list_deployments_all_namespaces(self, mock_get):
        # Patch the config methods directly
        with patch.object(k8s_config, 'get_api_url', return_value="https://k8s-remote:6443"), \
             patch.object(k8s_config, 'get_headers', return_value={"Authorization": "Bearer token"}), \
             patch.object(k8s_config, 'get_verify_ssl', return_value=False):

            # Mock API response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "items": [
                    {
                        "metadata": {
                            "name": "dep1",
                            "namespace": "ns1",
                            "creationTimestamp": "2023-01-01T00:00:00Z"
                        },
                        "spec": {"replicas": 3},
                        "status": {
                            "readyReplicas": 3,
                            "updatedReplicas": 3,
                            "availableReplicas": 3
                        }
                    },
                    {
                        "metadata": {
                            "name": "dep2",
                            "namespace": "ns2",
                            "creationTimestamp": "2023-01-02T00:00:00Z"
                        },
                        "spec": {"replicas": 1},
                        "status": {
                            "readyReplicas": 0,
                            "updatedReplicas": 1,
                            "availableReplicas": 0
                        }
                    }
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Run tool
            result = self.list_tool.run()

            # Verify
            self.assertTrue(result['success'])
            self.assertEqual(result['count'], 2)
            self.assertEqual(result['deployments'][0]['name'], 'dep1')
            self.assertEqual(result['deployments'][0]['namespace'], 'ns1')
            self.assertEqual(result['deployments'][1]['name'], 'dep2')
            self.assertEqual(result['deployments'][1]['namespace'], 'ns2')
            
            # Verify API call
            mock_get.assert_called_with(
                "https://k8s-remote:6443/apis/apps/v1/deployments",
                headers={"Authorization": "Bearer token"},
                verify=False,
                timeout=10
            )

    @patch('devops_agent.k8s_tools.remote_k8s_extended_tools.requests.get')
    def test_list_deployments_specific_namespace(self, mock_get):
        with patch.object(k8s_config, 'get_api_url', return_value="https://k8s-remote:6443"), \
             patch.object(k8s_config, 'get_headers', return_value={"Authorization": "Bearer token"}), \
             patch.object(k8s_config, 'get_verify_ssl', return_value=False):
            
            # Mock API response
            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_get.return_value = mock_response

            # Run tool
            result = self.list_tool.run(namespace="my-ns")

            # Verify API call
            mock_get.assert_called_with(
                "https://k8s-remote:6443/apis/apps/v1/namespaces/my-ns/deployments",
                headers={"Authorization": "Bearer token"},
                verify=False,
                timeout=10
            )
            self.assertTrue(result['success'])
            self.assertEqual(result['count'], 0)

    @patch('devops_agent.k8s_tools.remote_k8s_extended_tools.requests.get')
    def test_describe_deployment(self, mock_get):
        with patch.object(k8s_config, 'get_api_url', return_value="https://k8s-remote:6443"), \
             patch.object(k8s_config, 'get_headers', return_value={"Authorization": "Bearer token"}), \
             patch.object(k8s_config, 'get_verify_ssl', return_value=False):

            # Mock API response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "metadata": {
                    "name": "my-dep",
                    "namespace": "default",
                    "creationTimestamp": "2023-01-01T00:00:00Z",
                    "labels": {"app": "my-app"},
                    "annotations": {}
                },
                "spec": {
                    "replicas": 3,
                    "strategy": {"type": "RollingUpdate"},
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "nginx",
                                    "image": "nginx:latest",
                                    "ports": [{"containerPort": 80}]
                                }
                            ]
                        }
                    }
                },
                "status": {
                    "readyReplicas": 3,
                    "updatedReplicas": 3,
                    "availableReplicas": 3,
                    "conditions": [
                        {"type": "Available", "status": "True", "message": "Deployment is available"}
                    ]
                }
            }
            mock_get.return_value = mock_response

            # Run tool
            result = self.describe_tool.run(deployment_name="my-dep", namespace="default")

            # Verify
            self.assertTrue(result['success'])
            dep = result['deployment']
            self.assertEqual(dep['name'], 'my-dep')
            self.assertEqual(dep['namespace'], 'default')
            self.assertEqual(dep['replicas_desired'], 3)
            self.assertEqual(dep['containers'][0]['name'], 'nginx')
            self.assertEqual(dep['containers'][0]['ports'], [80])
            
            # Verify API call
            mock_get.assert_called_with(
                "https://k8s-remote:6443/apis/apps/v1/namespaces/default/deployments/my-dep",
                headers={"Authorization": "Bearer token"},
                verify=False,
                timeout=10
            )

if __name__ == '__main__':
    unittest.main()
