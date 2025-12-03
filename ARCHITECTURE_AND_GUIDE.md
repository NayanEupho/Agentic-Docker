# Agentic Docker: Deep Dive & Architecture Guide

This document provides a comprehensive explanation of the Agentic Docker project, how it works under the hood, and a detailed guide to its components, specifically focusing on the Multi-MCP (Model Context Protocol) architecture.

---

## 1. Introduction: What is Agentic Docker?

**Agentic Docker** is an intelligent command-line tool that allows you to control Docker and Kubernetes clusters using **natural language**. Instead of remembering complex CLI commands like `docker run -d -p 8080:80 nginx` or `kubectl get pods -n kube-system`, you can simply type:

> "Start nginx on port 8080"
>
> "Show me the pods in the system namespace"

### Core Philosophy
The project is built on the idea of **AI Agents**. An agent is a system that can:
1.  **Perceive**: Understand your intent from natural language.
2.  **Reason**: Decide which tool is best suited to fulfill your request.
3.  **Act**: Execute the tool safely.
4.  **Feedback**: Report the results back to you.

---

## 2. Core Concepts

To understand how this works, we need to define a few key terms:

### 🧠 LLM (Large Language Model)
The "brain" of the operation. We use **Ollama** to run models like `phi3:mini` locally on your machine. The LLM doesn't execute code itself; it just *thinks*. It takes your text and maps it to a specific function (tool) it knows about.

### 🔌 MCP (Model Context Protocol)
This is the standard "language" used for communication between the Agent and the actual tools.
- **Why use it?** It decouples the AI from the tools. The AI doesn't need to know *how* to list Docker containers; it just needs to know that a tool called `docker_list_containers` exists and follows a specific schema.
- **Structure:** It uses JSON-RPC (Remote Procedure Call). The Agent sends a JSON object saying "Call function X with args Y", and the Server replies with "Here is the result Z".

### 🤖 The Agent
The orchestrator code (`agent.py`). It sits in the middle, talking to the User, the LLM, and the MCP Servers.

---

## 3. Architecture Overview

The system is designed as a **Multi-MCP Architecture**. This means we have separate servers for different domains (Docker, Local K8s, Remote K8s), running concurrently.

```mermaid
graph TD
    User[User Input] -->|1. Natural Language| CLI[CLI (Typer)]
    CLI -->|2. Pass Query| Agent[Agent Orchestrator]
    
    subgraph "The Brain"
        Agent -->|3. Get Tool Decision| LLM[Ollama (phi3:mini)]
        LLM -->|4. Return Tool Name & Args| Agent
    end
    
    subgraph "Routing Layer"
        Agent -->|5. Check Tool Prefix| Router{Routing Logic}
        Router -->|'docker_'| ClientDocker[Docker Client]
        Router -->|'k8s_'| ClientLocal[Local K8s Client]
        Router -->|'remote_k8s_'| ClientRemote[Remote K8s Client]
    end
    
    subgraph "Execution Layer (MCP Servers)"
        ClientDocker -->|JSON-RPC (Port 8080)| ServerDocker[Docker MCP Server]
        ClientLocal -->|JSON-RPC (Port 8081)| ServerLocal[Local K8s MCP Server]
        ClientRemote -->|JSON-RPC (Port 8082)| ServerRemote[Remote K8s MCP Server]
    end
    
    subgraph "Infrastructure"
        ServerDocker -->|Docker SDK| DockerEngine[Docker Engine]
        ServerLocal -->|kubectl| LocalCluster[Local K8s Cluster]
        ServerRemote -->|kubectl| RemoteCluster[Remote K8s Cluster]
    end
    
    DockerEngine -->|Result| ServerDocker
    ServerDocker -->|Result| Agent
    Agent -->|6. Format & Display| User
```

---

## 4. The Lifecycle of a Command

Let's trace exactly what happens when you run a command.

### Scenario: "List my local pods"

#### Step 1: Initialization (`start-all`)
Before you run a query, you execute `agentic-docker start-all`.
- **Triggers:** `cli.py` spawns 3 separate subprocesses.
- **Process 1:** Starts `server.py` on `localhost:8080` (Docker).
- **Process 2:** Starts `k8s_server.py` on `localhost:8081` (Local K8s).
- **Process 3:** Starts `remote_k8s_server.py` on `localhost:8082` (Remote K8s).
- **Status:** All servers are now listening for JSON-RPC connections.

#### Step 2: User Input
You type:
```bash
agentic-docker run "Show me the pods in the default namespace"
```

#### Step 3: Tool Aggregation
The Agent needs to tell the LLM what tools are available.
- It queries the Docker Registry -> Gets `docker_list_containers`, `docker_run...`
- It queries the Local K8s Registry -> Gets `k8s_list_pods`, `k8s_list_nodes`
- It queries the Remote K8s Registry -> Gets `remote_k8s_list_pods`, `remote_k8s_list_nodes`
- **Result:** A massive list of JSON schemas is sent to the LLM.

#### Step 4: LLM Decision
The LLM analyzes your prompt: "Show me the pods..."
- It looks at the list of tools.
- It sees `k8s_list_pods` matches "pods" and "local" (implied or explicit).
- **Output:** It returns a JSON object:
  ```json
  {
    "name": "k8s_list_pods",
    "arguments": { "namespace": "default" }
  }
  ```

#### Step 5: Intelligent Routing
The Agent receives the tool name `k8s_list_pods`.
- **Logic:**
  - Does it start with `remote_k8s_`? No.
  - Does it start with `k8s_`? **Yes.**
- **Action:** The Agent selects the **Local K8s MCP Client**.

#### Step 6: Execution (MCP)
- The Client constructs a JSON-RPC request:
  ```json
  {
    "jsonrpc": "2.0",
    "method": "call_tool",
    "params": {
      "name": "k8s_list_pods",
      "arguments": { "namespace": "default" }
    },
    "id": 1
  }
  ```
- It sends this via HTTP POST to `http://localhost:8081`.

#### Step 7: The Server Acts
- The Local K8s Server receives the request.
- It looks up the Python function associated with `k8s_list_pods`.
- It executes the function (which internally runs `kubectl get pods -n default -o json`).
- It captures the output and returns it as a JSON response.

#### Step 8: User Feedback
- The Agent receives the raw JSON data (list of pods).
- It formats it into a readable string (adding emojis like 🟢 for running pods).
- **Final Output:**
  ```text
  ✅ Success! Found 2 pod(s) in namespace 'default' (LOCAL):
     🟢 nginx-pod (10.1.0.5) - Running [Ready: True]
     🔴 db-pod (10.1.0.6) - Error [Ready: False]
  ```

---

## 5. Detailed Component Breakdown

### 1. The CLI (`cli.py`)
- **Role:** The entry point. Uses `typer` to parse command line arguments.
- **Key Commands:**
  - `start-all`: The "master switch" that brings up the entire infrastructure.
  - `run`: The main interface for user interaction.
  - `server / k8s-server / remote-k8s-server`: Low-level commands to start individual servers (mostly used by `start-all`).

### 2. The Agent (`agent.py`)
- **Role:** The manager.
- **Responsibilities:**
  - **Context Management:** Aggregates tools from all sources.
  - **Safety:** Checks if a tool is "dangerous" (like `stop_container`) and asks for user confirmation via `safety.py`.
  - **Routing:** The traffic cop that directs requests to the right port.
  - **Formatting:** Turns raw data into pretty text.

### 3. The MCP Servers
We run three distinct servers to keep concerns separated. This makes the system more robust; if the K8s server crashes, Docker still works.

| Server | Port | Prefix | Responsibility |
|--------|------|--------|----------------|
| **Docker** | `8080` | `docker_` | Managing local containers, images, and volumes. |
| **Local K8s** | `8081` | `k8s_` | Interacting with the cluster defined in your local `~/.kube/config`. |
| **Remote K8s** | `8082` | `remote_k8s_` | Interacting with a secondary/remote cluster (configurable). |

---

## 6. Extending the System

Want to add a new capability? Here is the lifecycle of adding a new tool:

1.  **Define the Tool:** Create a new Python class in `tools/` or `k8s_tools/`.
2.  **Implement `run()`:** Write the actual logic (e.g., `subprocess.run("docker network ls")`).
3.  **Register the Tool:** Add it to the `ALL_TOOLS` list in `__init__.py`.
4.  **Restart Servers:** The Agent will automatically discover the new tool schema on the next run.
5.  **Use it:** The LLM will now "know" about your new tool and can select it when you ask.

---

## 7. Troubleshooting Common Issues

- **"I ask for remote pods but it lists local ones"**
  - **Cause:** The LLM might be confused.
  - **Fix:** Be more specific. Say "remote cluster" or "remote machine" explicitly. The routing relies on the LLM selecting the tool with the `remote_` prefix.

- **"Connection Refused"**
  - **Cause:** One of the MCP servers isn't running.
  - **Fix:** Check the terminal where you ran `start-all`. Are all 3 windows open? Did one close with an error?

- **"Unicode/Emoji Errors on Windows"**
  - **Cause:** Windows Command Prompt has poor UTF-8 support.
  - **Fix:** Use Windows Terminal or PowerShell, or set `PYTHONIOENCODING=utf-8`.
