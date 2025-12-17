# devops_agent/__init__.py
"""
Agentic Docker Package Initialization

This file initializes the devops_agent package and provides convenient
imports and version information. It makes the package structure available
for import and can serve as the main entry point for package-level functionality.
"""

# Package metadata
__version__ = "1.0.0"
__author__ = "Agentic Docker Development Team"
__description__ = "AI-powered Docker assistant using natural language commands"

# Optional: Define what gets imported when someone does "from devops_agent import *"
__all__ = [
    "run_command",
    "start_server",
    "process_query",
    "__version__"
]

# Optional: Provide convenient imports for common functionality
def get_version():
    """
    Get the current version of the Agentic Docker package.
    
    Returns:
        str: The version string in format "major.minor.patch"
    """
    return __version__

def get_package_info():
    """
    Get comprehensive package information.
    
    Returns:
        dict: Dictionary containing version, author, and description
    """
    return {
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "name": "devops_agent"
    }

# Optional: Initialize any package-level configuration or setup
def initialize():
    """
    Initialize package-level configuration.
    
    This function can be called to set up any package-level settings,
    though for this application it's mostly a placeholder for future use.
    """
    # Currently no initialization needed, but kept for extensibility
    pass

# Call initialize on package import (optional)
initialize()

# Optional: Provide a main entry point function
def main():
    """
    Main entry point for the package when run as a module.
    
    This function can be used to provide a direct way to run the CLI
    without going through the command line interface.
    """
    from .cli import main as cli_main
    return cli_main()

# Example usage when this package is imported:
"""
import devops_agent
print(devops_agent.get_version())  # "1.0.0"
info = devops_agent.get_package_info()
print(info['name'])  # "devops_agent"
"""