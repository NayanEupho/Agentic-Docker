import sys
import os
import time
from devops_agent.mcp.client import call_k8s_tool

print("Testing Remote K8s Integration...")

# Test List Nodes
print("\n1. Testing k8s_list_nodes...")
result = call_k8s_tool("k8s_list_nodes", {})
if result.get("success"):
    print(f"SUCCESS: Found {result.get('count')} nodes.")
    for node in result.get("nodes", [])[:3]:
        print(f" - {node['name']} ({node['status']}) - {node['internal_ip']}")
else:
    print(f"FAILURE: {result.get('error')}")

# Test List Pods
print("\n2. Testing k8s_list_pods (default namespace)...")
result = call_k8s_tool("k8s_list_pods", {"namespace": "default"})
if result.get("success"):
    print(f"SUCCESS: Found {result.get('count')} pods.")
    for pod in result.get("pods", [])[:3]:
        print(f" - {pod['name']} ({pod['phase']})")
else:
    print(f"FAILURE: {result.get('error')}")
