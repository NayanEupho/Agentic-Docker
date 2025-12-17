
import asyncio
import time
from agentic_docker.agent import process_query_async
from agentic_docker.dspy_client import init_dspy

async def main():
    print("🚀 Starting Latency Debug...")
    
    # Pre-init to separate init time
    t0 = time.time()
    try:
        init_dspy()
        print(f"⏱️ [PERF] DSPy Init: {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"⚠️ Init failed: {e}")
        
    print("\n--- Running Query: 'list local pods' ---")
    
    # Run query
    result = await process_query_async("list local pods")
    
    print("\n--- Result ---")
    print(result["output"][:200] + "...") # Truncate output

if __name__ == "__main__":
    asyncio.run(main())
