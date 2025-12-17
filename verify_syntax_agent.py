
try:
    from agentic_docker.agent_module import DockerAgent
    from agentic_docker.agent import process_query_async
    print("✅ Syntax Check Passed")
except Exception as e:
    print(f"❌ Syntax Error: {e}")
