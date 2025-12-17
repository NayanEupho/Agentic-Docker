import dspy
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Default model
DEFAULT_MODEL = "llama3.2"

def init_dspy():
    """
    Initialize DSPy with the configured Ollama model.
    """
    model_name = os.getenv("AGENTIC_LLM_MODEL", DEFAULT_MODEL)
    print(f"🧠 Initializing DSPy with Ollama model: {model_name}")
    
    # Configure dspy.LM (DSPy 3.0+)
    # Uses LiteLLM under the hood: model='ollama/model_name'
    print(f"   (Using dspy.LM with ollama/{model_name})")
    try:
    # LiteLLM/Ollama requires a non-empty API key to avoid header errors, 
        # even though it's not used for auth locally.
        host = os.getenv("AGENTIC_LLM_HOST", "http://localhost:11434")
        lm = dspy.LM(f"ollama/{model_name}", api_base=host, api_key="ollama")
    except Exception as e:
        print(f"⚠️ Error initializing dspy.LM: {e}")
        # Fallback for older versions or different setup?
        # Re-raise for now
        raise e
    
    dspy.settings.configure(lm=lm)
    return lm
