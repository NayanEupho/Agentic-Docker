# agentic_docker/k8s_tools/k8s_list_pods.py
"""
Kubernetes List Pods Tool

This tool allows the LLM to list Kubernetes pods in a specific namespace or across all namespaces.
It uses HTTP requests to the Kubernetes API (configured via k8s_config).
"""

# Import requests library for HTTP communication with K8s API
import requests
# Import our base K8sTool class that this tool must inherit from
from .k8s_base import K8sTool
# Import configuration
from .k8s_config import k8s_config
# Import typing utilities for type hints
from typing import Dict, Any

class LocalK8sListPodsTool(K8sTool):
    """
    Tool for listing Kubernetes pods in the LOCAL cluster.
    
    This tool can list:
    - Pods in a specific namespace (default: "default")
    - Pods across all namespaces
    
    It communicates with the Kubernetes API via the configured URL.
    """
    
    # Define the unique name for this tool
    # This name will be used by the LLM to call this specific tool
    name = "k8s_list_pods"
    
    # Provide a human-readable description of what this tool does
    # The LLM will use this description to understand when to use this tool
    description = "List Kubernetes pods in a namespace or across all namespaces"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Define the JSON Schema for this tool's parameters.
        
        This tool accepts optional parameters:
        - 'namespace': string - the namespace to list pods from (default: "default")
        - 'all_namespaces': boolean - if True, list pods from all namespaces
        - 'node_name': string - (Optional) List only pods running on this specific node.
        
        The schema follows JSON Schema specification and tells the LLM
        what arguments this tool can accept.
        """
        return {
            # This is a JSON Schema object definition
            "type": "object",
            # Properties that the tool accepts
            "properties": {
                # 'namespace' parameter: string type, defaults to "default"
                "namespace": {
                    "type": "string",
                    "default": "default",
                    "description": "The Kubernetes namespace to list pods from. Defaults to 'default'."
                },
                # 'all_namespaces' parameter: boolean type, defaults to False
                "all_namespaces": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, list pods from all namespaces. Overrides the 'namespace' parameter."
                },
                # 'node_name' parameter: string type, optional
                "node_name": {
                    "type": "string",
                    "description": "Filter pods by node name. Example: 'kc-m1'."
                }
            },
            # List of required parameters (empty list means all parameters are optional)
            "required": []
        }

    def run(self, namespace: str = "default", all_namespaces: bool = False, node_name: str = None) -> Dict[str, Any]:
        """
        Execute the actual Kubernetes command to list pods.
        
        This method makes an HTTP GET request to the Kubernetes API
        to retrieve pod information, then formats the result.
        
        Args:
            namespace (str): The namespace to list pods from (default: "default")
            all_namespaces (bool): If True, list pods from all namespaces (default: False)
            node_name (str): Optional node name to filter by.
        
        Returns:
            dict: A structured result containing either:
                  - success: True, pods: [list of pod info], count: number of pods
                  - success: False, error: [error message]
        """
        api_url = k8s_config.get_api_url()
        headers = k8s_config.get_headers()
        verify_ssl = k8s_config.get_verify_ssl()

        try:
            # Determine the API endpoint based on whether we want all namespaces
            if all_namespaces:
                # List pods across all namespaces
                url = f"{api_url}/api/v1/pods"
            else:
                # List pods in a specific namespace
                url = f"{api_url}/api/v1/namespaces/{namespace}/pods"
            
            # Prepare query parameters
            params = {}
            if node_name:
                # Use fieldSelector to filter by node name
                params['fieldSelector'] = f"spec.nodeName={node_name}"
            
            # Make the HTTP GET request to the Kubernetes API
            # We disable SSL warning if verify is False
            if not verify_ssl:
                requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

            response = requests.get(url, headers=headers, params=params, verify=verify_ssl, timeout=10)
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            data = response.json()
            
            # Extract pods from the response
            pods_list = data.get("items", [])
            
            # Format the pod information into a list of dictionaries
            # Each dictionary contains essential information about a pod
            formatted_pods = []
            for pod in pods_list:
                # Extract metadata and status information
                metadata = pod.get("metadata", {})
                status = pod.get("status", {})
                spec = pod.get("spec", {})
                
                # Create a dictionary with pod information
                pod_info = {
                    # Pod name
                    "name": metadata.get("name", "unknown"),
                    # Namespace the pod belongs to
                    "namespace": metadata.get("namespace", "unknown"),
                    # Pod phase (Running, Pending, Succeeded, Failed, Unknown)
                    "phase": status.get("phase", "Unknown"),
                    # Pod IP address
                    "pod_ip": status.get("podIP", "N/A"),
                    # Node the pod is running on
                    "node": spec.get("nodeName", "N/A"),
                    # Number of containers in the pod
                    "containers": len(spec.get("containers", [])),
                    # Ready status
                    "ready": self._get_ready_status(status),
                }
                
                # Add this pod's info to our list
                formatted_pods.append(pod_info)
            
            # Return successful result with the list of pods
            return {
                "success": True,
                "pods": formatted_pods,
                "count": len(formatted_pods),
                "namespace": "all" if all_namespaces else namespace,
                "filtered_by_node": node_name
            }
            
        except requests.exceptions.ConnectionError:
            # Handle the case where the API is not reachable
            return {
                "success": False,
                "error": f"Cannot connect to Kubernetes API at {api_url}. "
                        "Check your network connection and configuration.",
                "pods": []
            }
            
        except requests.exceptions.Timeout:
            # Handle request timeout
            return {
                "success": False,
                "error": "Request to Kubernetes API timed out after 10 seconds",
                "pods": []
            }
            
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors (404, 403, etc.)
            return {
                "success": False,
                "error": f"Kubernetes API returned error: {e.response.status_code} - {e.response.reason}",
                "pods": []
            }
            
        except Exception as e:
            # If anything else goes wrong, catch the exception and return an error
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "pods": []
            }
    
    def _get_ready_status(self, status: Dict[str, Any]) -> str:
        """
        Helper method to determine if a pod is ready.
        
        Args:
            status (dict): The status section from the pod spec
            
        Returns:
            str: Ready status as a string (e.g., "2/2", "0/1")
        """
        conditions = status.get("conditions", [])
        container_statuses = status.get("containerStatuses", [])
        
        if not container_statuses:
            return "0/0"
        
        # Count ready containers
        ready_count = sum(1 for cs in container_statuses if cs.get("ready", False))
        total_count = len(container_statuses)
        
        return f"{ready_count}/{total_count}"
