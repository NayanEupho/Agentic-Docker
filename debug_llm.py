from agentic_docker.llm.ollama_client import get_tool_calls
from agentic_docker.tools import get_tools_schema
from agentic_docker.k8s_tools import get_k8s_tools_schema
from agentic_docker.k8s_tools.remote_k8s_tools import get_remote_k8s_tools_schema
import json

def debug_llm_response():
    query = "list pods in the nodejs namespace in remote k8s"
    
    docker_tools_schema = get_tools_schema()
    k8s_tools_schema = get_k8s_tools_schema()
    remote_k8s_tools_schema = get_remote_k8s_tools_schema()
    all_tools_schema = docker_tools_schema + k8s_tools_schema + remote_k8s_tools_schema
    
    print(f"Query: {query}")
    print("-" * 20)
    
    tool_calls = get_tool_calls(query, all_tools_schema)
    
    print("-" * 20)
    print("Parsed Tool Calls:")
    print(json.dumps(tool_calls, indent=2))

if __name__ == "__main__":
    debug_llm_response()
