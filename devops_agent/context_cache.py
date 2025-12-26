
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ResourceEntity:
    name: str
    kind: str # Pod, Node, Service
    details: Dict[str, Any] # IP, Status, Image, etc.
    timestamp: float

class ContextCache:
    """
    In-memory cache for 'Short-Term Episodic Memory' of resources.
    Keyed by Session ID.
    PROPERTIES:
    - Ephemeral: Clears on restart.
    - TTL: Data expires after X seconds (default 60s) to prevent staleness.
    - Intent: Used to answer "What is its IP?" without API calls.
    """
    _instance = None
    
    # Structure: { session_id: { resource_name: ResourceEntity } }
    _cache: Dict[str, Dict[str, ResourceEntity]] = {}
    
    # Structure: { session_id: "mcp_id" }
    _last_mcp_map: Dict[str, str] = {}
    
    TTL_SECONDS = 60 * 5 # 5 Minutes memory (Generous for a chat session)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ContextCache, cls).__new__(cls)
        return cls._instance

    def update(self, session_id: str, resources: List[Dict[str, Any]]):
        """
        Update memory with new observations.
        resources: List of dicts, e.g. [{"kind": "Pod", "name": "web-1", "ip": "10.0.0.1", "status": "Running"}]
        """
        if not session_id: return
        
        if session_id not in self._cache:
            self._cache[session_id] = {}
        
        now = time.time()
        for res in resources:
            name = res.get("name")
            if not name: continue
            
            # Store
            entity = ResourceEntity(
                name=name,
                kind=res.get("kind", "Unknown"),
                details=res,
                timestamp=now
            )
            self._cache[session_id][name] = entity
            # print(f"[Memory] Memorized {name} ({res.get('kind')}) for session {session_id[:8]}")

    def get_context_block(self, session_id: str) -> str:
        """
        Returns a formatted string for the LLM Prompt.
        Filters out expired items.
        """
        if not session_id or session_id not in self._cache:
            return ""
        
        session_memory = self._cache[session_id]
        now = time.time()
        
        # Prune expired
        keys_to_delete = [k for k, v in session_memory.items() if (now - v.timestamp) > self.TTL_SECONDS]
        for k in keys_to_delete:
            del session_memory[k]
        
        if not session_memory:
            return ""
            
        # Format for LLM
        # We want a concise JSON-like block
        # "web-pod-1": {"IP": "10.0.0.1", "Status": "Running"}
        
        memory_dict = {}
        for name, entity in session_memory.items():
            # Minimal details to save tokens
            memory_dict[name] = entity.details
            
        import json
        return json.dumps(memory_dict, indent=2)

    def clear(self, session_id: str):
        if session_id in self._cache:
            del self._cache[session_id]
        if session_id in self._last_mcp_map:
            del self._last_mcp_map[session_id]
            
    def set_last_mcp(self, session_id: str, mcp: str):
        if session_id and mcp:
            self._last_mcp_map[session_id] = mcp
            
    def get_last_mcp(self, session_id: str) -> Optional[str]:
        return self._last_mcp_map.get(session_id)

# Singleton instance
_cache_instance = None
def get_context_cache():
    global _cache_instance
    if not _cache_instance:
        _cache_instance = ContextCache()
    return _cache_instance

context_cache = get_context_cache()
