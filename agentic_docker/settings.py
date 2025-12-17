import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class AgenticSettings(BaseSettings):
    """
    Centralized configuration for Agentic Docker.
    Reads from environment variables, .env file, and defaults.
    """
    # LLM Configuration
    LLM_MODEL: str = "llama3.2"
    LLM_HOST: str = "http://localhost:11434"
    LLM_TEMPERATURE: float = 0.1
    
    # Server Configuration
    MCP_SERVER_HOST: str = "127.0.0.1"
    
    # Ports (default to separate ports for isolation)
    DOCKER_PORT: int = 8080
    LOCAL_K8S_PORT: int = 8081
    REMOTE_K8S_PORT: int = 8082
    
    # Safety
    SAFETY_CONFIRM: bool = True
    
    # Load from .env file if present
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        env_prefix="AGENTIC_"  # Variables must start with AGENTIC_, e.g., AGENTIC_LLM_MODEL
    )

# Instantiate global settings object
settings = AgenticSettings()
