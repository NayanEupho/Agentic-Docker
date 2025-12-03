# agentic_docker/k8s_tools/remote_k8s_tools.py
"""
Remote Kubernetes Tools Registry

This module defines the tools for the remote Kubernetes cluster.
It wraps the existing K8s tools but renames them to avoid conflict with local tools.
"""

from typing import List, Dict, Any
from .k8s_base import K8sTool
from .k8s_list_pods import K8sListPodsTool
from .k8s_list_nodes import K8sListNodesTool

# We create subclasses to override the name and description
class RemoteK8sListPodsTool(K8sListPodsTool):
    name = "remote_k8s_list_pods"
    description = "List Kubernetes pods in the REMOTE cluster (10.20.4.221)"

class RemoteK8sListNodesTool(K8sListNodesTool):
    name = "remote_k8s_list_nodes"
    description = "List Kubernetes nodes in the REMOTE cluster (10.20.4.221)"

# Registry of remote tools
ALL_REMOTE_K8S_TOOLS: List[K8sTool] = [
    RemoteK8sListPodsTool(),
    RemoteK8sListNodesTool(),
]

def get_remote_k8s_tools_schema() -> List[dict]:
    """
    Generate the JSON Schema for all available Remote Kubernetes tools.
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.get_parameters_schema()
        }
        for tool in ALL_REMOTE_K8S_TOOLS
    ]

def find_remote_k8s_tool_by_name(name: str) -> K8sTool:
    for tool in ALL_REMOTE_K8S_TOOLS:
        if tool.name == name:
            return tool
    return None
