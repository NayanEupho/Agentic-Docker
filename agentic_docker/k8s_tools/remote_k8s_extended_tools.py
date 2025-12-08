# agentic_docker/k8s_tools/remote_k8s_extended_tools.py
"""
Extended Remote Kubernetes Tools

This module implements additional tools for the remote Kubernetes cluster:
1. List Namespaces
2. Find Pod Namespace
3. Get Resource IPs (Pods/Nodes)
"""

import requests
from typing import Dict, Any, List
from .k8s_base import K8sTool
from .k8s_config import k8s_config

class RemoteK8sListNamespacesTool(K8sTool):
    name = "remote_k8s_list_namespaces"
    description = "List all namespaces available in the REMOTE Kubernetes cluster with their status."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        try:
            url = f"{k8s_config.get_api_url()}/api/v1/namespaces"
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            namespaces = []
            for item in data.get('items', []):
                namespaces.append({
                    "name": item['metadata']['name'],
                    "status": item['status']['phase'],
                    "creation_timestamp": item['metadata']['creationTimestamp']
                })

            return {
                "success": True,
                "namespaces": namespaces,
                "count": len(namespaces)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sFindPodNamespaceTool(K8sTool):
    name = "remote_k8s_find_pod_namespace"
    description = "Find which namespace(s) a specific pod or list of pods belongs to in the REMOTE cluster."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pod_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of pod names to search for."
                }
            },
            "required": ["pod_names"]
        }

    def run(self, pod_names: List[str], **kwargs) -> Dict[str, Any]:
        try:
            # We need to list pods across all namespaces to find matches
            url = f"{k8s_config.get_api_url()}/api/v1/pods"
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            results = {}
            all_pods = data.get('items', [])
            
            for target_pod in pod_names:
                found_namespaces = []
                for pod in all_pods:
                    if pod['metadata']['name'] == target_pod:
                        found_namespaces.append(pod['metadata']['namespace'])
                
                if found_namespaces:
                    results[target_pod] = found_namespaces
                else:
                    results[target_pod] = "Not Found"

            return {
                "success": True,
                "pod_locations": results
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sGetResourcesIPsTool(K8sTool):
    name = "remote_k8s_get_resources_ips"
    description = "Get IP addresses and ports for specific pods or nodes in the REMOTE cluster."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["pod", "node"],
                    "description": "Type of resource to look up (pod or node)."
                },
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of resource names."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to search in (only for pods). Defaults to all namespaces if not specified."
                }
            },
            "required": ["resource_type", "names"]
        }

    def run(self, resource_type: str, names: List[str], namespace: str = None, **kwargs) -> Dict[str, Any]:
        try:
            results = {}
            
            if resource_type == "pod":
                # If namespace is provided, search there. Otherwise search all.
                if namespace:
                    url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{namespace}/pods"
                else:
                    url = f"{k8s_config.get_api_url()}/api/v1/pods"
            elif resource_type == "node":
                url = f"{k8s_config.get_api_url()}/api/v1/nodes"
            else:
                return {"success": False, "error": "Invalid resource_type. Must be 'pod' or 'node'."}

            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            items = data.get('items', [])

            for target_name in names:
                found = False
                for item in items:
                    if item['metadata']['name'] == target_name:
                        found = True
                        ip_info = {}
                        
                        if resource_type == "pod":
                            ip_info["pod_ip"] = item['status'].get('podIP', "Pending")
                            ip_info["host_ip"] = item['status'].get('hostIP', "Unknown")
                            # Extract ports if available in container specs
                            ports = []
                            for container in item['spec'].get('containers', []):
                                for port_spec in container.get('ports', []):
                                    ports.append(f"{port_spec.get('containerPort')}/{port_spec.get('protocol', 'TCP')}")
                            ip_info["ports"] = ports
                            
                        elif resource_type == "node":
                            addresses = item['status'].get('addresses', [])
                            for addr in addresses:
                                ip_info[addr['type']] = addr['address']
                        
                        results[target_name] = ip_info
                        break # Stop searching for this name once found (assuming unique names per ns/cluster)
                
                if not found:
                    results[target_name] = "Not Found"

            return {
                "success": True,
                "ips": results
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sListDeploymentsTool(K8sTool):
    """
    Tool to list Kubernetes deployments in a remote cluster.
    
    This tool interacts with the Kubernetes API to fetch deployment resources.
    It supports listing deployments from all namespaces or a specific namespace.
    It extracts key information like replicas, status, and creation time to present
    a summary to the user.
    """
    name = "remote_k8s_list_deployments"
    description = "List Kubernetes deployments in the REMOTE cluster. Can list for a specific namespace or all namespaces."

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Define the JSON schema for the tool's parameters.
        
        Returns:
            Dict[str, Any]: JSON Schema object describing 'namespace' parameter.
        """
        return {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list deployments from. If omitted, lists from all namespaces."
                }
            },
            "required": []
        }

    def run(self, namespace: str = None, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool to list deployments.

        Args:
            namespace (str, optional): The namespace to filter by. Defaults to None (all namespaces).
            **kwargs: Additional arguments (unused).

        Returns:
            Dict[str, Any]: A dictionary containing success status, list of deployments, and count.
        """
        try:
            # Construct the API URL based on whether a namespace is provided
            # If namespace is None, we query the cluster-wide endpoint: /apis/apps/v1/deployments
            # If namespace is provided, we query the namespaced endpoint: /apis/apps/v1/namespaces/{ns}/deployments
            if namespace:
                url = f"{k8s_config.get_api_url()}/apis/apps/v1/namespaces/{namespace}/deployments"
            else:
                url = f"{k8s_config.get_api_url()}/apis/apps/v1/deployments"

            # Make the HTTP GET request to the Remote Kubernetes API
            # We use the configuration from k8s_config to get headers (auth token) and SSL verification settings
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            
            # Check for HTTP errors (e.g., 401 Unauthorized, 404 Not Found)
            response.raise_for_status()
            
            # Parse the JSON response from Kubernetes
            data = response.json()

            deployments = []
            # Iterate through the 'items' list in the response, which contains the Deployment objects
            for item in data.get('items', []):
                # Extract metadata (name, namespace, creation timestamp)
                metadata = item.get('metadata', {})
                # Extract status (current state of replicas)
                status = item.get('status', {})
                # Extract spec (desired state)
                spec = item.get('spec', {})
                
                # Append a simplified dictionary for each deployment
                deployments.append({
                    "name": metadata.get('name'),
                    "namespace": metadata.get('namespace'),
                    "replicas": spec.get('replicas', 0), # Desired number of replicas
                    "ready_replicas": status.get('readyReplicas', 0), # Number of ready pods
                    "updated_replicas": status.get('updatedReplicas', 0), # Number of pods with latest version
                    "available_replicas": status.get('availableReplicas', 0), # Number of available pods
                    "creation_timestamp": metadata.get('creationTimestamp')
                })

            # Return the success result with the list of deployments
            return {
                "success": True,
                "deployments": deployments,
                "count": len(deployments),
                "scope": f"namespace '{namespace}'" if namespace else "all namespaces"
            }
        except Exception as e:
            # Handle any exceptions (network errors, API errors, parsing errors)
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sDescribeDeploymentTool(K8sTool):
    """
    Tool to get detailed information about a specific deployment in a remote cluster.
    
    This tool fetches the full manifest of a deployment and extracts comprehensive details
    including strategy, container images, ports, and status conditions.
    """
    name = "remote_k8s_describe_deployment"
    description = "Get detailed information about a specific deployment in the REMOTE cluster."

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Define the JSON schema for the tool's parameters.
        
        Returns:
            Dict[str, Any]: JSON Schema object describing 'deployment_name' and 'namespace' parameters.
        """
        return {
            "type": "object",
            "properties": {
                "deployment_name": {
                    "type": "string",
                    "description": "Name of the deployment to describe."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the deployment. Defaults to 'default' if not specified."
                }
            },
            "required": ["deployment_name"]
        }

    def run(self, deployment_name: str, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        """
        Execute the tool to describe a deployment.

        Args:
            deployment_name (str): The name of the deployment.
            namespace (str, optional): The namespace. Defaults to "default".
            **kwargs: Additional arguments (unused).

        Returns:
            Dict[str, Any]: A dictionary containing success status and detailed deployment info.
        """
        try:
            # Construct the API URL for the specific deployment resource
            # Endpoint: /apis/apps/v1/namespaces/{namespace}/deployments/{name}
            url = f"{k8s_config.get_api_url()}/apis/apps/v1/namespaces/{namespace}/deployments/{deployment_name}"
            
            # Make the HTTP GET request
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            
            # Check for errors (e.g., 404 if deployment doesn't exist)
            response.raise_for_status()
            
            # Parse the JSON response
            data = response.json()

            # Extract essential details from the Kubernetes resource object
            metadata = data.get('metadata', {})
            spec = data.get('spec', {})
            status = data.get('status', {})
            
            # Extract container details from the pod template
            # This gives us information about what images and ports are being used
            containers = []
            pod_template = spec.get('template', {}).get('spec', {})
            for container in pod_template.get('containers', []):
                containers.append({
                    "name": container.get('name'),
                    "image": container.get('image'),
                    "ports": [p.get('containerPort') for p in container.get('ports', [])]
                })

            # Construct a comprehensive details dictionary
            details = {
                "name": metadata.get('name'),
                "namespace": metadata.get('namespace'),
                "labels": metadata.get('labels', {}),
                "annotations": metadata.get('annotations', {}),
                "creation_timestamp": metadata.get('creationTimestamp'),
                "replicas_desired": spec.get('replicas', 0),
                "replicas_ready": status.get('readyReplicas', 0),
                "replicas_available": status.get('availableReplicas', 0),
                "replicas_updated": status.get('updatedReplicas', 0),
                "strategy": spec.get('strategy', {}).get('type'), # e.g., RollingUpdate
                "containers": containers,
                "conditions": status.get('conditions', []) # e.g., Available, Progressing
            }

            return {
                "success": True,
                "deployment": details
            }
        except Exception as e:
            # Handle exceptions
            return {
                "success": False,
                "error": str(e)
            }
