# devops_agent/k8s_tools/remote_k8s_service_tools.py
"""
Remote Kubernetes Service Tools

This module implements tools to interact with Kubernetes Services (svc) in a remote cluster.
"""

import requests
from typing import Dict, Any, List
from urllib.parse import quote
from .k8s_base import K8sTool
from .k8s_config import k8s_config

class RemoteK8sListServicesTool(K8sTool):
    """
    Tool to list Kubernetes services in a remote cluster.
    """
    name = "remote_k8s_list_services"
    description = "List Kubernetes Services (svc). Can list all services in a SPECIFIC NAMESPACE (e.g. 'kube-system') or across ALL namespaces. Use this for general listing/overview."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list services from. Defaults to 'default'."
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "If true, list services from all namespaces."
                }
            },
            "required": []
        }

    def run(self, namespace: str = "default", all_namespaces: bool = False, **kwargs) -> Dict[str, Any]:
        try:
            # Handle empty string namespace from LLM
            if not namespace and not all_namespaces:
                namespace = "default"

            # Construct API URL
            if all_namespaces:
                url = f"{k8s_config.get_api_url()}/api/v1/services" 
            elif namespace:
                 safe_ns = quote(namespace)
                 url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/services"
            else:
                 # Fallback (should be covered by top check, but safe to keep)
                 url = f"{k8s_config.get_api_url()}/api/v1/namespaces/default/services"

            # Make Request
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # Parse results
            services = []
            for item in data.get('items', []):
                metadata = item.get('metadata', {})
                spec = item.get('spec', {})
                status = item.get('status', {})
                
                ports = []
                for p in spec.get('ports', []):
                    ports.append(f"{p.get('port')}:{p.get('targetPort')}/{p.get('protocol')}")

                services.append({
                    "name": metadata.get('name'),
                    "namespace": metadata.get('namespace'),
                    "type": spec.get('type'),
                    "cluster_ip": spec.get('clusterIP'),
                    "external_ips": spec.get('externalIPs', []),
                    "ports": ports,
                    "creation_timestamp": metadata.get('creationTimestamp')
                })

            return {
                "success": True,
                "services": services,
                "count": len(services),
                "scope": "all namespaces" if all_namespaces else f"namespace '{namespace}'"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sGetServiceTool(K8sTool):
    """
    Tool to get detailed info about a specific Kubernetes service.
    """
    name = "remote_k8s_get_service"
    description = "Get detailed configuration/status for a SINGLE SPECIFIC Kubernetes Service. REQUIRED: User MUST provide the service name explicitly (e.g. 'get service pos'). If no name is given, do NOT guess. Use list_services instead if name is unknown."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service to retrieve."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the service. Defaults to 'default'."
                }
            },
            "required": ["service_name"]
        }

    def run(self, service_name: str = None, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        if not service_name:
            return {
                "success": False,
                "error": "Service name is required. To list services, use remote_k8s_list_services instead."
            }
        
        # Handle empty string namespace from LLM
        if not namespace: 
            namespace = "default"

        try:
            safe_name = quote(service_name)
            safe_ns = quote(namespace)
            
            url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/services/{safe_name}"

            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            metadata = data.get('metadata', {})
            spec = data.get('spec', {})
            status = data.get('status', {})

            # Detailed info
            details = {
                "name": metadata.get('name'),
                "namespace": metadata.get('namespace'),
                "labels": metadata.get('labels', {}),
                "annotations": metadata.get('annotations', {}),
                "selector": spec.get('selector', {}),
                "type": spec.get('type'),
                "cluster_ip": spec.get('clusterIP'),
                "external_ips": spec.get('externalIPs', []),
                "load_balancer_ip": status.get('loadBalancer', {}).get('ingress', []),
                "ports": spec.get('ports', []),
                "session_affinity": spec.get('sessionAffinity')
            }

            return {
                "success": True,
                "service": details
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

class RemoteK8sDescribeServiceTool(K8sTool):
    """
    Tool to describe a Kubernetes service.
    """
    name = "remote_k8s_describe_service"
    description = "DESCRIBE a service. Returns detailed configuration, status, endpoints (if possible via endpoints API), and event log. Use when user asks 'describe service <name>'."
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service."
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace. Defaults to 'default'."
                }
            },
            "required": ["service_name"]
        }

    def run(self, service_name: str, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        try:
            safe_name = quote(service_name)
            safe_ns = quote(namespace)
            
            # 1. Get Service Details
            url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/services/{safe_name}"
            response = requests.get(
                url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # 2. Get Events
            events_url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/events?fieldSelector=involvedObject.name={safe_name},involvedObject.namespace={safe_ns},involvedObject.kind=Service"
            events_resp = requests.get(
                events_url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            events = []
            if events_resp.ok:
                for e in events_resp.json().get('items', []):
                    events.append({
                        "type": e.get('type'),
                        "reason": e.get('reason'),
                        "message": e.get('message'),
                        "count": e.get('count', 1),
                        "last_timestamp": e.get('lastTimestamp')
                    })
            
            # 3. Get Endpoints (Optional but helpful for describe service)
            ep_url = f"{k8s_config.get_api_url()}/api/v1/namespaces/{safe_ns}/endpoints/{safe_name}"
            ep_resp = requests.get(
                ep_url,
                headers=k8s_config.get_headers(),
                verify=k8s_config.get_verify_ssl(),
                timeout=10
            )
            endpoints_list = []
            if ep_resp.ok:
                ep_data = ep_resp.json()
                for subset in ep_data.get('subsets', []):
                    for addr in subset.get('addresses', []):
                        endpoints_list.append(f"{addr.get('ip')}")

            metadata = data.get('metadata', {})
            spec = data.get('spec', {})
            status = data.get('status', {})

            details = {
                "name": metadata.get('name'),
                "namespace": metadata.get('namespace'),
                "labels": metadata.get('labels', {}),
                "annotations": metadata.get('annotations', {}),
                "selector": spec.get('selector', {}),
                "type": spec.get('type'),
                "cluster_ip": spec.get('clusterIP'),
                "external_ips": spec.get('externalIPs', []),
                "ports": spec.get('ports', []),
                "endpoints": endpoints_list,
                "events": events
            }

            return {
                "success": True,
                "service": details
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
