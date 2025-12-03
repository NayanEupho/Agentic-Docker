# Agentic Docker

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-required-blue)
![Ollama](https://img.shields.io/badge/ollama-required-orange)

An AI-powered Docker assistant that understands natural language commands. This project demonstrates the use of local Large Language Models (LLMs) via [Ollama](https://ollama.com/) to interpret human-readable instructions and safely execute corresponding Docker operations using the Model Context Protocol (MCP).

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Available Commands](#available-commands)
- [Safety Features](#safety-features)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

- **Natural Language Processing:** Control Docker using plain English (e.g., "Start nginx on port 8080").
- **Local LLM:** Uses Ollama for privacy and offline capability. No external API calls for inference.
- **MCP Protocol:** Implements the Model Context Protocol for secure and standardized tool calling between the LLM and Docker operations.
- **Safety Layer:** Confirmation prompts for potentially destructive operations (e.g., stopping containers).
- **Modular Design:** Easy to extend with new Docker commands by adding new tool classes.
- **Docker SDK:** Safe, programmatic interaction with Docker using the official Python SDK, avoiding raw shell command injection.

## Architecture

```mermaid
graph TD
    User[User] -->|Natural Language Command| CLI[CLI (Typer)]
    CLI -->|Query| Agent[Agent Orchestrator]
    Agent -->|1. Select Tool| LLM[LLM (Ollama)]
    LLM -->|Tool Call JSON| Agent
    Agent -->|2. Safety Check| Safety[Safety Layer]
    Safety -->|Confirmation?| User
    Safety -->|Approved| MCP_Client[MCP Client]
    
    subgraph Routing Logic
        MCP_Client -->|docker_*| DockerServer[Docker MCP Server (8080)]
        MCP_Client -->|k8s_*| LocalK8sServer[Local K8s MCP Server (8081)]
        MCP_Client -->|remote_k8s_*| RemoteK8sServer[Remote K8s MCP Server (8082)]
    end
    
    DockerServer -->|Execute| Docker[Docker Engine]
    LocalK8sServer -->|Execute| LocalK8s[Local K8s Cluster]
    RemoteK8sServer -->|Execute| RemoteK8s[Remote K8s Cluster]
    
    DockerServer -->|Result| Agent
    LocalK8sServer -->|Result| Agent
    RemoteK8sServer -->|Result| Agent
    Agent -->|Format Result| User
```

## Prerequisites

- **Python 3.9 or higher:** Required for the project's dependencies.
- **Docker Engine:** Must be installed and running on your machine.
- **Ollama:** Must be installed to run local LLMs. Download from [https://ollama.com/](https://ollama.com/).
- **`phi3:mini` Model:** The system is configured to use the `phi3:mini` model by default.
- **Kubernetes Cluster (Optional):** For K8s commands, you need a local cluster (e.g., Minikube, Docker Desktop) and `kubectl` configured.
- **Remote K8s Access (Optional):** For remote K8s commands, you need access to the remote cluster.

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd agentic-docker
    ```

2.  **Create and Activate a Virtual Environment:**
    ```bash
    # Create the virtual environment
    python -m venv .venv

    # Activate it on Windows (Command Prompt)
    .\.venv\Scripts\activate

    # OR activate it on Windows (PowerShell)
    .\.venv\Scripts\Activate.ps1

    # OR activate it on macOS/Linux
    source .venv/bin/activate
    ```

3.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    # OR install the package in development mode (recommended)
    pip install -e .
    ```

## Usage

The system requires two main components to be running simultaneously: the Ollama service (providing the LLM) and the Agentic Docker MCP servers.

### Step 1: Start Ollama Service

Open a **new terminal** window/tab.

1.  Navigate to the project directory and activate the virtual environment.
2.  **Important for Corporate Networks:** Set proxy bypass variables.
3.  Start the Ollama service:
    ```bash
    ollama serve
    ```

### Step 2: Start MCP Servers

Open **another new terminal** window/tab.

1.  Navigate to the project directory and activate the virtual environment.
2.  Start ALL servers (Docker, Local K8s, Remote K8s) at once:
    ```bash
    agentic-docker start-all
    ```
    This will launch 3 separate processes in new windows:
    - Docker MCP Server (Port 8080)
    - Local K8s MCP Server (Port 8081)
    - Remote K8s MCP Server (Port 8082)

    *Alternatively, you can start them individually:*
    ```bash
    agentic-docker server --port 8080
    agentic-docker k8s-server --port 8081
    agentic-docker remote-k8s-server --port 8082
    ```

### Step 3: Run Commands

Open **a third terminal** window/tab for running your commands.

1.  Navigate to the project directory and activate the virtual environment.
2.  Use natural language to control Docker and Kubernetes:

    **Docker Commands:**
    ```bash
    agentic-docker run "List all containers"
    agentic-docker run "Start nginx on port 8080"
    ```

    **Local Kubernetes Commands:**
    ```bash
    agentic-docker run "Show me the running nodes in my local machine"
    agentic-docker run "List pods in default namespace"
    ```

    **Remote Kubernetes Commands:**
    ```bash
    agentic-docker run "Show me the running nodes in remote cluster"
    agentic-docker run "List pods in remote cluster"
    ```

## Configuration

The default LLM model is `phi3:mini`. You can change this by modifying `agentic_docker/llm/ollama_client.py`.

## Available Commands

### Core CLI Commands

- `agentic-docker start-all`: **Recommended.** Starts all 3 MCP servers (Docker, Local K8s, Remote K8s) in separate processes.
- `agentic-docker run "<query>"`: Executes a command based on the natural language query.
- `agentic-docker status`: Checks the status of the LLM connection, MCP servers, and available tools.
- `agentic-docker list-tools`: Lists all available tools.

### Server Commands (for manual control)

- `agentic-docker server`: Starts the Docker MCP server (default port 8080).
- `agentic-docker k8s-server`: Starts the Local Kubernetes MCP server (default port 8081).
- `agentic-docker remote-k8s-server`: Starts the Remote Kubernetes MCP server (default port 8082).

### Natural Language Examples

- **Docker:** `"Start nginx"`, `"Stop container my-nginx"`, `"List containers"`
- **Local K8s:** `"List local nodes"`, `"Show pods in kube-system"`
- **Remote K8s:** `"List remote nodes"`, `"Show remote pods"`

### Options for `run` Command

- `--verbose, -v`: Show detailed processing information.
- `--no-confirm, -y`: Skip safety confirmation prompts (use with caution!).

## Safety Features

- **Confirmation Prompts:** Destructive operations prompt for confirmation.
- **Input Validation:** Arguments are validated using Pydantic models.
- **Safe Execution:** Uses official SDKs where possible.

## Project Structure

```
agentic-docker/
├── agentic_docker/           # Main Python package
│   ├── __init__.py
│   ├── cli.py                # Command-Line Interface (Typer)
│   ├── agent.py              # Orchestrates LLM, tools, safety
│   ├── safety.py             # Confirmation logic
│   ├── mcp/                  # Model Context Protocol components
│   │   ├── __init__.py
│   │   ├── server.py         # Docker MCP server
│   │   ├── k8s_server.py     # Local K8s MCP server
│   │   ├── remote_k8s_server.py # Remote K8s MCP server
│   │   └── client.py         # MCP client with routing logic
│   ├── tools/                # Docker tool definitions
│   ├── k8s_tools/            # Kubernetes tool definitions
│   └── llm/                  # LLM interaction components
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Package build configuration
└── README.md                 # This file
```

## Troubleshooting

- **"Cannot connect to MCP server..."**: Ensure you have run `agentic-docker start-all` or the specific server command.
- **"LLM not available..."**: Ensure `ollama serve` is running.
- **"UnicodeEncodeError"**: On Windows, you might see emoji encoding errors in some terminals. Try using a terminal that supports UTF-8 (like Windows Terminal) or set `PYTHONIOENCODING=utf-8`.
