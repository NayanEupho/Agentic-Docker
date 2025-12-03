# agentic_docker/k8s_tools/k8s_config.py
"""
Configuration module for Kubernetes tools.

This module holds the configuration for connecting to the Kubernetes API.
It allows switching between local proxy mode (default) and remote cluster mode.
"""

from typing import Optional, Dict

class K8sConfig:
    """
    Singleton configuration for Kubernetes tools.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(K8sConfig, cls).__new__(cls)
            cls._instance.reset()
        return cls._instance
    
    def reset(self):
        """Reset configuration to defaults (local proxy)."""
        self.api_url = "http://127.0.0.1:8001"
        self.token = None
        self.verify_ssl = True
        self.headers = {}

    def configure_remote(self, api_url: str, token: str, verify_ssl: bool = False):
        """
        Configure for a remote Kubernetes cluster.
        
        Args:
            api_url (str): The base URL of the Kubernetes API (e.g., "https://10.20.4.221:16443")
            token (str): The Bearer token for authentication
            verify_ssl (bool): Whether to verify SSL certificates (default: False for self-signed)
        """
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.verify_ssl = verify_ssl
        self.headers = {
            "Authorization": f"Bearer {token}"
        }

    def get_api_url(self) -> str:
        return self.api_url

    def get_headers(self) -> Dict[str, str]:
        return self.headers

    def get_verify_ssl(self) -> bool:
        return self.verify_ssl

# Global instance
k8s_config = K8sConfig()
