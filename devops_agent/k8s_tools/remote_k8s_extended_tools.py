# devops_agent/k8s_tools/remote_k8s_extended_tools.py
"""
Extended Remote Kubernetes Tools

This module implements additional tools for the remote Kubernetes cluster:
1. List Namespaces
2. Find Pod Namespace
3. Get Resource IPs (Pods/Nodes)
"""

import requests
from typing import Dict, Any, List
from urllib.parse import quote
from .k8s_base import K8sTool
from .k8s_config import k8s_config
from .k8s_utils import safe_k8s_request

class RemoteK8sListNamespacesTool(K8sTool):
    name = "remote_k8s_list_namespaces"
    description = "List all namespaces available in the REMOTE Kubernetes cluster with their status."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "label_selector": {
                    "type": "string",
                    "description": "Filter namespaces by labels. Use standard Kubernetes label selector syntax."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of namespaces to return. Default is 50."
                }
            },
            "required": []
        }

    def run(self, label_selector: str = None, limit: int = 50, **kwargs) -> Dict[str, Any]:
        url = f"{k8s_config.get_api_url()}/api/v1/namespaces"
        
        params = {}
        if label_selector: params['labelSelector'] = label_selector
        if limit: params['limit'] = limit
        
        if params:
            import urllib.parse
            url += "?" + urllib.parse.urlencode(params)

        res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
        if not res["success"]:
            return res

        data = res["data"]
        namespaces = []
        for item in data.get('items', []):
            metadata = item.get('metadata', {})
            status = item.get('status', {})
            namespaces.append({
                "name": metadata.get('name'),
                "status": status.get('phase'),
                "creation_timestamp": metadata.get('creationTimestamp')
            })

        return {
            "success": True,
            "namespaces": namespaces,
            "count": len(namespaces)
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
        # SANITIZATION: Handle LLM returning string "['a','b']" instead of list
        if isinstance(pod_names, str):
            import json
            try:
                 # LLM often uses single quotes for lists logic "['a']" which is invalid JSON
                 cleaned_names = pod_names.replace("'", '"')
                 pod_names = json.loads(cleaned_names)
            except json.JSONDecodeError:
                 return {"success": False, "error": f"Invalid format for pod_names: {pod_names}"}

        # We need to list pods across all namespaces to find matches
        url = f"{k8s_config.get_api_url()}/api/v1/pods"
        # Note: safe_k8s_request doesn't take params yet, I'll update it or append to url
        if "?" in url: url += "&limit=500"
        else: url += "?limit=500"
        res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())

        if not res["success"]:
            return res

        data = res["data"]
        results = {}
        for pod_name in pod_names:
            results[pod_name] = "Not Found"
            for item in data.get('items', []):
                if item.get('metadata', {}).get('name') == pod_name:
                    results[pod_name] = item.get('metadata', {}).get('namespace')
                    break
        
        return {
            "success": True,
            "pod_namespaces": results
        }

class RemoteK8sGetResourcesIPsTool(K8sTool):
    name = "remote_k8s_get_resources_ips"
    description = "Get ONLY the IP addresses (InternalIP, ExternalIP) for specific pods or nodes. USE THIS TOOL whenever the user asks for 'IP', 'address', or 'network' details. It is faster and more specific than describing the whole node."

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
                    "description": "List of resource names. OPTIONAL: If omitted or empty, fetches IPs for ALL resources of that type."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to search in (only for pods). Defaults to all namespaces if not specified."
                }
            },
            "required": ["resource_type"]
        }

    def run(self, resource_type: str, names: List[str] = None, namespace: str = None, **kwargs) -> Dict[str, Any]:
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

            # Sanitize names if provided
            if names:
                if isinstance(names, str):
                    import json
                    try:
                         cleaned_names = names.replace("'", '"')
                         names = json.loads(cleaned_names)
                         # If json.loads returns a string (e.g. from input '"kc-m1"'), wrap it
                         if isinstance(names, str):
                             names = [names]
                    except json.JSONDecodeError:
                         # Fallback: If it's just a raw string like "kc-m1" (not JSON), treat as single name
                         names = [names]
            else:
                names = [] # Handle None case

            res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
            if not res["success"]:
                return res
            data = res["data"]
            items = data.get('items', [])
            
            # If names is empty (or meant to be all), we populate it with all names found
            if not names:
                names = [i['metadata']['name'] for i in items]

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
                },
                "label_selector": {
                    "type": "string",
                    "description": "Filter deployments by labels. Use standard Kubernetes label selector syntax."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of deployments to return. Default is 50."
                }
            },
            "required": []
        }

    def run(self, namespace: str = None, label_selector: str = None, limit: int = 50, **kwargs) -> Dict[str, Any]:
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

            # Prepare query parameters
            params = {}
            if label_selector:
                params['labelSelector'] = label_selector
            if limit:
                params['limit'] = limit

            # Make the HTTP GET request to the Remote Kubernetes API
            # We use the configuration from k8s_config to get headers (auth token) and SSL verification settings
            res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl(), params=params)
            
            if not res["success"]:
                return res
            
            # Parse the JSON response from Kubernetes
            data = res["data"]

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
            safe_name = quote(deployment_name)
            safe_namespace = quote(namespace)
            url = f"{k8s_config.get_api_url()}/apis/apps/v1/namespaces/{safe_namespace}/deployments/{safe_name}"
            
            # Make the HTTP GET request
            res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
            
            if not res["success"]:
                return res
            
            # Parse the JSON response
            data = res["data"]

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
            # Handle any exceptions (network errors, API errors, parsing errors)
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sDescribeNodeTool(K8sTool):
    """
    Tool to get detailed information about a specific node in a remote Kubernetes cluster.
    
    This tool fetches comprehensive information similar to 'kubectl describe node <node_name>',
    including capacity, allocatable resources, conditions, addresses, and running pods summary.
    """
    name = "remote_k8s_describe_node"
    description = "DESCRIBE a node (like 'kubectl describe node'). Returns full details: CPU/memory capacity, conditions (Ready/DiskPressure), OS info, taints. Use this when user says 'describe node' or wants node details."

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Define the JSON schema for the tool's parameters.
        
        Returns:
            Dict[str, Any]: JSON Schema object describing 'node_name' parameter.
        """
        return {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "REQUIRED: The exact node name to describe. Extract from conversation context (e.g., if user says 'first node' and you know nodes are kc-m1, kc-w1, etc., provide 'kc-m1')."
                }
            },
            "required": ["node_name"]
        }

    def run(self, node_name: str, **kwargs) -> Dict[str, Any]:
        from .k8s_utils import safe_k8s_request
        safe_name = quote(node_name)
        url = f"{k8s_config.get_api_url()}/api/v1/nodes/{safe_name}"
        
        res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
        if not res["success"]:
            return res

        data = res["data"]
        metadata = data.get('metadata', {})
        status = data.get('status', {})
        spec = data.get('spec', {})

        details = {
            "name": metadata.get('name'),
            "labels": metadata.get('labels', {}),
            "annotations": metadata.get('annotations', {}),
            "creation_timestamp": metadata.get('creationTimestamp'),
            "status": {
                "conditions": status.get('conditions', []),
                "addresses": status.get('addresses', []),
                "capacity": status.get('capacity', {}),
                "allocatable": status.get('allocatable', {}),
                "node_info": status.get('nodeInfo', {})
            },
            "spec": {
                "pod_cidr": spec.get('podCIDR'),
                "unschedulable": spec.get('unschedulable', False),
                "taints": spec.get('taints', [])
            }
        }

        return {
            "success": True,
            "node": details
        }

class RemoteK8sListPodsOnNodeTool(K8sTool):
    """
    Tool to list pods running on a specific node in a remote Kubernetes cluster.
    """
    name = "remote_k8s_list_pods_on_node"
    description = "List all pods running on a specific node in the REMOTE Kubernetes cluster."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "REQUIRED: The name of the node to list pods from."
                }
            },
            "required": ["node_name"]
        }

    def run(self, node_name: str, **kwargs) -> Dict[str, Any]:
        from .k8s_utils import safe_k8s_request
        url = f"{k8s_config.get_api_url()}/api/v1/pods"
        res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl(), params={"fieldSelector": f"spec.nodeName={node_name}"})
        
        if not res["success"]:
            return res

        data = res["data"]
        pods = []
        for item in data.get('items', []):
            metadata = item.get('metadata', {})
            status = item.get('status', {})
            pods.append({
                "name": metadata.get('name'),
                "namespace": metadata.get('namespace'),
                "status": status.get('phase'),
                "pod_ip": status.get('podIP')
            })

        return {
            "success": True,
            "node_name": node_name,
            "pods": pods,
            "count": len(pods)
        }


class RemoteK8sDescribePodTool(K8sTool):
    """
    Tool to get detailed information about a specific pod in a remote cluster.
    """
    name = "remote_k8s_describe_pod"
    description = "DESCRIBE a pod. Returns comprehensive details including status, containers, images, restart counts, conditions, and events. Use this when the user asks to 'describe pod <name>'."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pod_name": {
                    "type": "string",
                    "description": "Name of the pod to describe."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the pod. Defaults to 'default'."
                }
            },
            "required": ["pod_name"]
        }

    def run(self, pod_name: str, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        try:
            safe_name = quote(pod_name)
            safe_ns = quote(namespace)
            
            # 1. Get Pod Details
            url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/pods/{safe_name}"
            res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
            if not res["success"]:
                return res
            pod_data = res["data"]

            # 2. Get Pod Events (for a true 'describe' feel)
            # Events are usually filtered by involvedObject using fieldSelector
            events_url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/events?fieldSelector=involvedObject.name={safe_name},involvedObject.namespace={safe_ns},involvedObject.uid={pod_data['metadata']['uid']}"
            
            events_res = safe_k8s_request("GET", events_url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
            events = []
            if events_res["success"]:
                for e in events_res["data"].get('items', []):
                    events.append({
                        "type": e.get('type'),
                        "reason": e.get('reason'),
                        "message": e.get('message'),
                        "count": e.get('count', 1),
                        "last_timestamp": e.get('lastTimestamp')
                    })

            # Formatting Response
            metadata = pod_data.get('metadata', {})
            spec = pod_data.get('spec', {})
            status = pod_data.get('status', {})

            containers = []
            for c_spec in spec.get('containers', []):
                # find corresponding status
                c_status = next((CS for CS in status.get('containerStatuses', []) if CS['name'] == c_spec['name']), {})
                containers.append({
                    "name": c_spec['name'],
                    "image": c_spec['image'],
                    "ready": c_status.get('ready', False),
                    "restart_count": c_status.get('restartCount', 0),
                    "state": c_status.get('state', {}),
                    "ports": [p.get('containerPort') for p in c_spec.get('ports', [])]
                })

            details = {
                "name": metadata.get('name'),
                "namespace": metadata.get('namespace'),
                "node_name": spec.get('nodeName'),
                "start_time": status.get('startTime'),
                "phase": status.get('phase'),
                "pod_ip": status.get('podIP'),
                "host_ip": status.get('hostIP'),
                "labels": metadata.get('labels', {}),
                "containers": containers,
                "conditions": status.get('conditions', []),
                "events": events
            }

            return {
                "success": True,
                "pod": details
            }
        except requests.exceptions.HTTPError as e:
            error_data = {"error": str(e)}
            try:
                if e.response is not None:
                    error_data["raw_error"] = e.response.json()
            except ValueError:
                pass
            return {
                "success": False,
                **error_data
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class RemoteK8sDescribeNamespaceTool(K8sTool):
    """
    Tool to describe a namespace.
    """
    name = "remote_k8s_describe_namespace"
    description = "DESCRIBE a namespace. Returns status, labels, and resource quotas (if implemented). Use when user asks 'describe namespace <name>'."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "namespace_name": {
                    "type": "string",
                    "description": "Name of the namespace."
                }
            },
            "required": ["namespace_name"]
        }

    def run(self, namespace_name: str, **kwargs) -> Dict[str, Any]:
        from .k8s_utils import safe_k8s_request
        safe_name = quote(namespace_name)
        url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_name}"
        
        res = safe_k8s_request("GET", url, k8s_config.get_headers(), k8s_config.get_verify_ssl())
        if not res["success"]:
            return res

        data = res["data"]
        metadata = data.get('metadata', {})
        status = data.get('status', {})

        return {
            "success": True,
            "namespace": {
                "name": metadata.get('name'),
                "status": status.get('phase'),
                "creation_timestamp": metadata.get('creationTimestamp'),
                "labels": metadata.get('labels', {}),
                "annotations": metadata.get('annotations', {})
            }
        }
