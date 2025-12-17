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

def init_dspy_lms():
    """
    Initialize DSPy with Smart and Fast variants.
    Returns: (fast_lm, smart_lm)
    """
    smart_model = settings.LLM_MODEL
    # Fallback to smart model if prompt/fast model not set (Option B: Silent Genius)
    fast_model = settings.LLM_FAST_MODEL or smart_model
    
    print(f"🧠 Initializing DSPy LMs:")
    print(f"   Smart: {smart_model}")
    print(f"   Fast:  {fast_model}")
    
    # 1. Ensure models
    _ensure_model(smart_model)
    if fast_model != smart_model:
        _ensure_model(fast_model)
        
    host = settings.LLM_HOST
    
    # 2. Create LMs
    # Note: dspy.LM might need specific kwargs depending on version. 
    # Current code used `api_base` and `api_key`.
    
    try:
        smart_lm = dspy.LM(f"ollama/{smart_model}", api_base=host, api_key="ollama")
    except Exception as e:
        print(f"⚠️ Error initializing Smart LM: {e}")
        smart_lm = None
        
    try:
        fast_lm = dspy.LM(f"ollama/{fast_model}", api_base=host, api_key="ollama")
    except Exception as e:
        print(f"⚠️ Error initializing Fast LM: {e}")
        fast_lm = smart_lm # Fallback
        
    # Configure global default to Smart (for CoT fallback stability)
    if smart_lm:
        dspy.settings.configure(lm=smart_lm)
        
    return fast_lm, smart_lm
