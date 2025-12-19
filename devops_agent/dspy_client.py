import dspy
import os
from .settings import settings
from .llm.ollama_client import get_client # Used for pulling

def _ensure_model(model_name: str):
    """Ensure model exists, pull if not."""
    try:
        from .llm.ollama_client import list_available_models
        models = list_available_models()
        # Simple substring check
        if not any(model_name in m for m in models):
            print(f"📦 Model '{model_name}' not found. Pulling... (This might take a while)")
            get_client().pull(model_name)
    except Exception as e:
        print(f"⚠️ Warning: Could not verify model '{model_name}': {e}")

# Global flag to track if DSPy has been configured
_DSPY_CONFIGURED = False

def init_dspy_lms():
    """
    Initialize DSPy with Smart and Fast variants.
    Returns: (fast_lm, smart_lm)
    """
    global _DSPY_CONFIGURED
    
    smart_model = settings.LLM_MODEL
    # Fallback to smart model if prompt/fast model not set (Option B: Silent Genius)
    fast_model = settings.LLM_FAST_MODEL or smart_model
    
    host = settings.LLM_HOST
    fast_host = settings.LLM_FAST_HOST or host
    
    # Only print initialization message once or if models change effectively
    # (simplification: just strictly once per process for now to avoid spam)
    if not _DSPY_CONFIGURED:
        print(f"🧠 Initializing DSPy LMs:")
        print(f"   Smart: {smart_model} ({host})")
        print(f"   Fast:  {fast_model} ({fast_host})")
    
    # 1. Ensure models (on their respective hosts)
    # Note: _ensure_model currently uses generic get_client() which uses LLM_HOST.
    # We need to ensure models exist on the Correct Host if they differ.
    # For now, we assume _ensure_model mostly checks the primary host or user ensured it.
    # Ideally update ensure_model to accept host arg.
    
    # 2. Create LMs
    
    try:
        smart_lm = dspy.LM(f"ollama/{smart_model}", api_base=host, api_key="ollama")
    except Exception as e:
        print(f"⚠️ Error initializing Smart LM: {e}")
        smart_lm = None
        
    try:
        fast_lm = dspy.LM(f"ollama/{fast_model}", api_base=fast_host, api_key="ollama")
    except Exception as e:
        print(f"⚠️ Error initializing Fast LM: {e}")
        fast_lm = smart_lm # Fallback
        
    # Configure global default to Smart (for CoT fallback stability)
    if smart_lm:
        # FIX: Only configure DSPy settings ONCE per process.
        # Calling dspy.settings.configure() multiple times from different async contexts
        # causes "can only be called from the same async task" errors in newer DSPy versions.
        if not _DSPY_CONFIGURED:
            dspy.settings.configure(lm=smart_lm)
            _DSPY_CONFIGURED = True
        
    return fast_lm, smart_lm
