import sys
import time
import requests
from devops_agent.agent import process_query

print("Testing Multi-Server Support...")

# 1. Test Local Docker
print("\n--- Testing Local Docker ---")
print("Query: 'Show me the running containers in my docker'")
result = process_query("Show me the running containers in my docker")
print(result)

# 2. Test Local Kubernetes
print("\n--- Testing Local Kubernetes ---")
print("Query: 'Show me the running nodes in my local machine'")
result = process_query("Show me the running nodes in my local machine")
print(result)

# 3. Test Remote Kubernetes
print("\n--- Testing Remote Kubernetes ---")
print("Query: 'Show me the running nodes in remote cluster'")
result = process_query("Show me the running nodes in remote cluster")
print(result)
