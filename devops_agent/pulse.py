
import asyncio
import time
import json
import os
from typing import Dict, Any, List, Optional
from .settings import settings

class InfrastructurePulse:
    """
    Proactive monitoring engine for DevOps Agent.
    Periodically fetches health/status of local and remote resources.
    Stores data for 'zero-latency' status checks and 'Instant Context'.
    """
    
    def __init__(self, intervals: Dict[str, float] = None):
        self.intervals = intervals or {
            "docker": 10.0,      # Check docker every 10s
            "k8s_local": 30.0,   # Check local k8s every 30s
            "k8s_remote": 60.0,  # Check remote k8s every 60s
            "global_index": 60.0 # Background search for resource names (Implicit Discovery)
        }
        self.status_cache: Dict[str, Any] = {
            "docker": {"status": "unknown", "data": {}, "last_check": 0},
            "k8s_local": {"status": "unknown", "data": {}, "last_check": 0},
            "k8s_remote": {"status": "unknown", "data": {}, "last_check": 0},
            "llm": {"status": "unknown", "last_check": 0},
            "embeddings": {"status": "unknown", "last_check": 0},
            "global_index": {"status": "ok", "resources": {}, "last_check": 0}
        }

        self._running = False
        self._task = None

    async def start(self):
        """Start the background monitoring loop."""
        if self._running: return
        self._running = True
        
        # Ensure we don't crash on Windows consoles that don't support emojis
        try:
            print("💓 [InfrastructurePulse] Started.")
        except UnicodeEncodeError:
            print("[InfrastructurePulse] Started.")
            
        self._task = asyncio.create_task(self._pulse_loop())

    async def stop(self):
        """Stop the background loop."""
        if not self._running: return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        try:
            print("💓 [InfrastructurePulse] Stopped.")
        except UnicodeEncodeError:
            print("[InfrastructurePulse] Stopped.")

    async def _pulse_loop(self):
        while self._running:
            tasks = []
            now = time.time()
            
            # Docker Check
            if now - self.status_cache["docker"]["last_check"] >= self.intervals["docker"]:
                tasks.append(self._check_docker())
                
            # Local K8s Check
            if now - self.status_cache["k8s_local"]["last_check"] >= self.intervals["k8s_local"]:
                tasks.append(self._check_k8s_local())
                
            # Remote K8s Check (Skip if user is disconnected)
            if now - self.status_cache["k8s_remote"]["last_check"] >= self.intervals["k8s_remote"]:
                 # Just to be safe, we can add a check if remote is reachable
                 pass
                 
            # LLM Check
            if now - self.status_cache["llm"]["last_check"] >= 60.0:
                tasks.append(self._check_llm())
            
            # Embeddings Check
            if now - self.status_cache["embeddings"]["last_check"] >= 60.0:
                tasks.append(self._check_embeddings())
            
            # Global Index Check (Implicit Discovery)
            if now - self.status_cache["global_index"]["last_check"] >= self.intervals["global_index"]:
                tasks.append(self._update_global_index())

            if tasks:
                await asyncio.gather(*tasks)
            
            await asyncio.sleep(1)

    async def _check_docker(self):
        try:
            from .mcp.client import call_tool_async
            result = await call_tool_async("docker_list_containers", {"all": True, "limit": 10})
            self.status_cache["docker"] = {
                "status": "connected" if result.get("success") is not False else "disconnected",
                "data": result,
                "last_check": time.time()
            }
        except Exception:
            self.status_cache["docker"]["status"] = "disconnected"
            self.status_cache["docker"]["last_check"] = time.time()

    async def _check_k8s_local(self):
        try:
            from .mcp.client import call_tool_async
            result = await call_tool_async("local_k8s_list_nodes", {})
            self.status_cache["k8s_local"] = {
                "status": "connected" if result.get("success") is not False else "disconnected",
                "data": result,
                "last_check": time.time()
            }
        except Exception:
            self.status_cache["k8s_local"]["status"] = "disconnected"
            self.status_cache["k8s_local"]["last_check"] = time.time()

    async def _check_llm(self):
        from .llm.ollama_client import check_model_access
        try:
            # check_model_access is sync, run in executor
            loop = asyncio.get_running_loop()
            is_up = await loop.run_in_executor(None, check_model_access, settings.LLM_HOST, settings.LLM_MODEL)
            self.status_cache["llm"] = {
                "status": "connected" if is_up else "disconnected",
                "last_check": time.time()
            }
        except Exception:
            self.status_cache["llm"]["status"] = "disconnected"
            self.status_cache["llm"]["last_check"] = time.time()

    async def _check_embeddings(self):
        from .llm.ollama_client import check_embedding_access
        try:
            loop = asyncio.get_running_loop()
            is_up = await loop.run_in_executor(None, check_embedding_access, settings.EMBEDDING_HOST, settings.EMBEDDING_MODEL)
            self.status_cache["embeddings"] = {
                "status": "connected" if is_up else "disconnected",
                "last_check": time.time()
            }
        except Exception:
            self.status_cache["embeddings"]["status"] = "disconnected"
            self.status_cache["embeddings"]["last_check"] = time.time()

    async def _update_global_index(self):
        """Builds/Updates a global map of resource names with TTL-based pruning."""
        from .mcp.client import call_tool_async
        
        # 1. Prune stale entries (items older than 5 minutes)
        # Pruning keeps the index lean for "Lightning Fast" memory performance.
        prune_threshold = time.time() - 300 
        
        current_index = self.status_cache["global_index"].get("resources", {"pods": {}, "nodes": {}, "deployments": {}})
        for category in ["pods", "deployments"]:
            keys_to_del = []
            for name, providers in current_index.get(category, {}).items():
                # If all providers for this name are stale, remove name
                if all(p.get("last_seen", 0) < prune_threshold for p in providers):
                    keys_to_del.append(name)
            for k in keys_to_del:
                del current_index[category][k]

        new_index = current_index
        
        # 2. Scanning helper
        async def scan_provider(provider_id: str):
            try:
                # Scan Pods
                pods_res = await call_tool_async(f"{provider_id}_list_pods", {"namespace": "default"})
                if isinstance(pods_res, dict) and pods_res.get("success"):
                    for p in pods_res.get("pods", []):
                        name, ns = p.get("name"), p.get("namespace", "default")
                        if name:
                            if name not in new_index["pods"]: new_index["pods"][name] = []
                            # Update or add
                            found = False
                            for entry in new_index["pods"][name]:
                                if entry["mcp"] == provider_id and entry["ns"] == ns:
                                    entry["last_seen"] = time.time()
                                    found = True
                                    break
                            if not found:
                                new_index["pods"][name].append({"mcp": provider_id, "ns": ns, "last_seen": time.time()})

                # Scan Deployments
                deploys_res = await call_tool_async(f"{provider_id}_list_deployments", {"namespace": "default"})
                if isinstance(deploys_res, dict) and deploys_res.get("success"):
                    for d in deploys_res.get("deployments", []):
                        name, ns = d.get("name"), d.get("namespace", "default")
                        if name:
                            if name not in new_index["deployments"]: new_index["deployments"][name] = []
                            found = False
                            for entry in new_index["deployments"][name]:
                                if entry["mcp"] == provider_id and entry["ns"] == ns:
                                    entry["last_seen"] = time.time()
                                    found = True
                                    break
                            if not found:
                                new_index["deployments"][name].append({"mcp": provider_id, "ns": ns, "last_seen": time.time()})
            except Exception:
                pass

        # Run scans in parallel
        await asyncio.gather(
            scan_provider("local_k8s"),
            scan_provider("remote_k8s")
        )
        
        self.status_cache["global_index"] = {
            "resources": new_index,
            "last_check": time.time()
        }
        print(f"💓 [Pulse] Global Index Updated & Pruned.")

    def get_status(self, provider: str) -> Dict[str, Any]:
        return self.status_cache.get(provider, {"status": "unknown"})

    def get_summary_block(self) -> str:
        """Returns a string description of infrastructure health for LLM context."""
        summary = ["--- Infrastructure Pulse ---"]
        for provider, info in self.status_cache.items():
            status = info.get("status", "unknown")  # Safe access with fallback
            last = int(time.time() - info["last_check"]) if info.get("last_check", 0) > 0 else "never"
            summary.append(f"- {provider.upper()}: {status} (Checked {last}s ago)")
            
            # If connected, add brief stats
            if status == "connected" and "data" in info:
                data = info["data"]
                if provider == "docker":
                    count = len(data) if isinstance(data, list) else 0
                    summary.append(f"  Recent: {count} containers visible.")
                elif "k8s" in provider:
                    count = len(data) if isinstance(data, list) else 0
                    summary.append(f"  Recent: {count} nodes detected.")
                    
        return "\n".join(summary)

# Singleton instance
_pulse_instance = None
def get_pulse():
    global _pulse_instance
    if not _pulse_instance:
        _pulse_instance = InfrastructurePulse()
    return _pulse_instance
