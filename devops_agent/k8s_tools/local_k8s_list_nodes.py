# devops_agent/k8s_tools/local_k8s_list_nodes.py
"""
Kubernetes List Nodes Tool

This tool allows the LLM to list Kubernetes nodes in the cluster.
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

class LocalK8sListNodesTool(K8sTool):
    """
    Tool for listing Kubernetes nodes in the LOCAL cluster.
    """
    name = "local_k8s_list_nodes"
    
    # Provide a human-readable description of what this tool does
    # The LLM will use this description to understand when to use this tool
    description = "List all Kubernetes nodes in the LOCAL cluster. Use this when user says 'local machine', 'local nodes', or just 'nodes' without specifying remote."
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Define the JSON Schema for this tool's parameters.
        
        This tool doesn't require any parameters - it always lists all nodes.
        
        The schema follows JSON Schema specification and tells the LLM
        what arguments this tool can accept.
        """
        return {
            # This is a JSON Schema object definition
            "type": "object",
            # No properties - this tool doesn't accept any parameters
            "properties": {},
            # List of required parameters (empty)
            "required": []
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the actual Kubernetes command to list nodes.
        
        This method makes an HTTP GET request to the Kubernetes API
        to retrieve node information, then formats the result.
        
        Args:
            **kwargs: No parameters expected, but accepts kwargs for consistency
        
        Returns:
            dict: A structured result containing either:
                  - success: True, nodes: [list of node info], count: number of nodes
                  - success: False, error: [error message]
        """
        api_url = k8s_config.get_api_url()
        headers = k8s_config.get_headers()
        verify_ssl = k8s_config.get_verify_ssl()

        try:
            # API endpoint for listing all nodes
            url = f"{api_url}/api/v1/nodes"
            
            # Make the HTTP GET request to the Kubernetes API
            # We disable SSL warning if verify is False
            if not verify_ssl:
                requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

            response = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            data = response.json()
            
            # Extract nodes from the response
            nodes_list = data.get("items", [])
            
            # Format the node information into a list of dictionaries
            # Each dictionary contains essential information about a node
            formatted_nodes = []
            for node in nodes_list:
                # Extract metadata and status information
                metadata = node.get("metadata", {})
                status = node.get("status", {})
                spec = node.get("spec", {})
                
                # Get node conditions to determine readiness
                conditions = status.get("conditions", [])
                ready_condition = next(
                    (c for c in conditions if c.get("type") == "Ready"),
                    {}
                )
                is_ready = ready_condition.get("status") == "True"
                
                # Get node roles from labels
                labels = metadata.get("labels", {})
                roles = self._get_node_roles(labels)
                
                # Get node addresses
                addresses = status.get("addresses", [])
                internal_ip = next(
                    (addr.get("address") for addr in addresses if addr.get("type") == "InternalIP"),
                    "N/A"
                )
                hostname = next(
                    (addr.get("address") for addr in addresses if addr.get("type") == "Hostname"),
                    "N/A"
                )
                
                # Get node capacity and allocatable resources
                capacity = status.get("capacity", {})
                allocatable = status.get("allocatable", {})
                
                # Create a dictionary with node information
                node_info = {
                    # Node name
                    "name": metadata.get("name", "unknown"),
                    # Node status (Ready/NotReady)
                    "status": "Ready" if is_ready else "NotReady",
                    # Node roles (e.g., "control-plane,master" or "worker")
                    "roles": roles,
                    # Internal IP address
                    "internal_ip": internal_ip,
                    # Hostname
                    "hostname": hostname,
                    # Kubernetes version running on the node
                    "kubelet_version": status.get("nodeInfo", {}).get("kubeletVersion", "unknown"),
                    # CPU capacity
                    "cpu": capacity.get("cpu", "N/A"),
                    # Memory capacity
                    "memory": capacity.get("memory", "N/A"),
                    # OS information
                    "os": status.get("nodeInfo", {}).get("osImage", "unknown"),
                }
                
                # Add this node's info to our list
                formatted_nodes.append(node_info)
            
            # Return successful result with the list of nodes
            return {
                "success": True,
                "nodes": formatted_nodes,
                "count": len(formatted_nodes)
            }
            
        except requests.exceptions.ConnectionError:
            # Handle the case where the API is not reachable
            return {
                "success": False,
                "error": f"Cannot connect to Kubernetes API at {api_url}. "
                        "Check your network connection and configuration.",
                "nodes": []
            }
            
        except requests.exceptions.Timeout:
            # Handle request timeout
            return {
                "success": False,
                "error": "Request to Kubernetes API timed out after 10 seconds",
                "nodes": []
            }
            
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors (404, 403, etc.)
            return {
                "success": False,
                "error": f"Kubernetes API returned error: {e.response.status_code} - {e.response.reason}",
                "nodes": []
            }
            
        except Exception as e:
            # If anything else goes wrong, catch the exception and return an error
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "nodes": []
            }
    
    def _get_node_roles(self, labels: Dict[str, Any]) -> str:
        """
        Helper method to extract node roles from labels.
        
        Args:
            labels (dict): The labels section from the node metadata
            
        Returns:
            str: Comma-separated list of roles (e.g., "control-plane,master" or "worker")
        """
        roles = []
        
        # Check for common role labels
        if "node-role.kubernetes.io/control-plane" in labels:
            roles.append("control-plane")
        if "node-role.kubernetes.io/master" in labels:
            roles.append("master")
        if "node-role.kubernetes.io/worker" in labels:
            roles.append("worker")
        
        # If no roles found, check for other role labels
        if not roles:
            for key in labels:
                if key.startswith("node-role.kubernetes.io/"):
                    role = key.replace("node-role.kubernetes.io/", "")
                    if role:
                        roles.append(role)
        
        # If still no roles, default to "worker"
        if not roles:
            roles.append("worker")
        
        return ",".join(roles)
