# devops_agent/k8s_tools/remote_k8s_tools.py
"""
Remote Kubernetes Tools Registry

This module defines the tools for the remote Kubernetes cluster.
It wraps the existing K8s tools but renames them to avoid conflict with local tools.
"""

from typing import List, Dict, Any
from .k8s_base import K8sTool
from .local_k8s_list_pods import LocalK8sListPodsTool
from .local_k8s_list_nodes import LocalK8sListNodesTool
from .remote_k8s_extended_tools import (
    RemoteK8sListNamespacesTool,
    RemoteK8sFindPodNamespaceTool,
    RemoteK8sGetResourcesIPsTool,
    RemoteK8sListDeploymentsTool,
    RemoteK8sDescribeDeploymentTool,
    RemoteK8sDescribeNodeTool,
    RemoteK8sDescribePodTool,
    RemoteK8sDescribeNamespaceTool
)
from .remote_k8s_service_tools import (
    RemoteK8sListServicesTool,
    RemoteK8sGetServiceTool,
    RemoteK8sDescribeServiceTool
)

# We create subclasses to override the name and description
class RemoteK8sListPodsTool(LocalK8sListPodsTool):
    name = "remote_k8s_list_pods"
    description = "List Kubernetes pods in the REMOTE cluster. Can filter by namespace or by node name (e.g., node_name='kc-m1')."

class RemoteK8sListNodesTool(LocalK8sListNodesTool):
    name = "remote_k8s_list_nodes"
    description = "List Kubernetes nodes in the REMOTE cluster (10.20.4.221). Use this ONLY when user specifies 'remote' or 'remote cluster'. For 'local machine', use local_k8s_list_nodes."

# Registry of remote tools
ALL_REMOTE_K8S_TOOLS: List[K8sTool] = [
    RemoteK8sListPodsTool(),
    RemoteK8sListNodesTool(),
    RemoteK8sListNamespacesTool(),
    RemoteK8sFindPodNamespaceTool(),
    RemoteK8sGetResourcesIPsTool(),
    RemoteK8sListDeploymentsTool(),
    RemoteK8sDescribeDeploymentTool(),
    RemoteK8sDescribeNodeTool(),
    RemoteK8sDescribePodTool(),
    RemoteK8sDescribeNamespaceTool(),
    RemoteK8sListServicesTool(),
    RemoteK8sGetServiceTool(),
    RemoteK8sDescribeServiceTool(),
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
