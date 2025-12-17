```mermaid
graph TD
    User[User Input] -->|1. Natural Language| CLI[CLI (Typer)]
    CLI -->|2. Pass Query| Agent[Agent Orchestrator]
    Agent -->|3. Inject Context| State[State Fetcher (Docker/K8s)]
    Agent -->|4. ReAct Loop| LLM[Ollama (Reasoning + Tool Call)]
    LLM -->|5. Return Thought & JSON| Agent
    Agent -->|6. Semantic Verification| Verifier[Validation Logic]
    Verifier -- Invalid? --> LLM
    Verifier -- Valid --> Router[Routing Logic]
    Router -->|docker_| ClientDocker[Docker Client]
    Router -->|k8s_| ClientLocal[Local K8s Client]
    Router -->|remote_k8s_| ClientRemote[Remote K8s Client]
    ClientDocker -->|JSON-RPC Port 8080| ServerDocker[Docker MCP Server]
    ClientLocal -->|JSON-RPC Port 8081| ServerLocal[Local K8s MCP Server]
    ClientRemote -->|JSON-RPC Port 8082| ServerRemote[Remote K8s MCP Server]
    ServerDocker -->|Docker SDK| DockerEngine[Docker Engine]
    ServerLocal -->|kubectl| LocalCluster[Local K8s Cluster]
    ServerRemote -->|kubectl| RemoteCluster[Remote K8s Cluster]
    DockerEngine -->|Result| ServerDocker
    ServerDocker -->|Result| Agent
    ServerLocal -->|Result| Agent
    ServerRemote -->|Result| Agent
    Agent -->|7. Format & Display| User

    subgraph Data Persistence
        SessionManager[Session Manager]
        SessionManager <-->|SQL Queries| DB[(SQLite Database)]
        Agent <-->|Read/Write History| SessionManager
    end
```

---

## 4. The Lifecycle of a Command

Let's trace exactly what happens when you run a command.

### Scenario: "Describe pod nginx-123"

#### Step 1: Initialization (Interactive)
Before you run a query, you execute `agentic-docker start-all`.
- **Interaction:** The CLI prompts you to select:
    1. **Host:** Local vs Remote/HPC.
    2. **Model:** "Hot Swap" selection of available models (e.g., `qwen2.5:72b` or `llama3.2`).
- **Triggers:** `cli.py` spawns 3 separate subprocesses with the selected configuration.
- **Process 1:** Starts `server.py` on `localhost:8080` (Docker).
- **Process 2:** Starts `k8s_server.py` on `localhost:8081` (Local K8s).
- **Process 3:** Starts `remote_k8s_server.py` on `localhost:8082` (Remote K8s).
- **Status:** All servers are now listening for JSON-RPC connections.

#### Step 2: User Input
You type:
```bash
agentic-docker run "Describe pod nginx-123"
```

#### Step 3: CLI Processing
- **Trigger:** `cli.py` receives the command via the `run` function.
- **Auto-Proxy:** The CLI automatically configures `NO_PROXY=localhost,127.0.0.1` to bypass corporate proxies.
- **Action:** The CLI calls `process_query()` with the user's query.

#### Step 4: Agent Processing
- **Trigger:** `agent.py` receives the query.
- **Action 1 (State Injection):** The Agent quickly (in parallel) fetches running containers and pods.
  - Context: `[System Context: Running Containers: web-app | Active Pods: frontend-7d8b]`
- **Action 2 (Logic Branching):**
  - **Fast Mode (Zero-Shot):** If the query is simple, the agent uses a fast, zero-shot prompt.
  - **Smart Mode (CoT):** If the query is complex or Fast Mode fails (invalid JSON), it switches to Chain-of-Thought reasoning.
- **Action 3 (Reasoning):**
  - *Thought:* "User wants details for pod nginx-123. Previous context shows it exists."
  - *Action:* `[{"name": "remote_k8s_describe_pod", "arguments": {"pod_name": "nginx-123"}}]`
- **Action 4 (Verification):** The Semantic Verifier checks tool names and arguments.
- **Action 5:** The Agent calls the tool via MCP Client.

#### Step 5: MCP Client Communication
- **Trigger:** `mcp/client.py` sends JSON-RPC request to Port 8082 (Remote K8s).

#### Step 6: MCP Server Execution
- **Trigger:** `mcp/remote_k8s_server.py` calls `RemoteK8sDescribePodTool`.
- **Action:** The tool fetches Pod metadata + Events + Container Status.
- **Action:** Returns a rich dictionary object.

#### Step 7: Result Formatting
- **Trigger:** The tool execution completes successfully.
- **Action:** The tool returns:
```json
{
  "success": true,
  "pod": { "name": "nginx-123", "events": [...], "containers": [...] }
}
```

#### Step 8: Agent Result Processing
- **Trigger:** The Agent receives the JSON-RPC response.
- **Action:** The `format_tool_result()` function detects the complex object and runs a specific formatter:
```
✅ Pod: nginx-123
   Node: kc-worker-1 | IP: 10.1.0.4 | Phase: Running
   Containers:
     🟢 nginx (nginx:latest)
       State: running | Restarts: 0
   Events (Recent):
     ℹ️ Scheduled: Successfully assigned to kc-worker-1
     ℹ️ Pulled: Container image "nginx" already present
```

#### Step 9: User Output
- **Trigger:** The CLI receives the formatted result.
- **Action:** The CLI prints the result to the terminal.
- **Output:** You see the detailed, human-readable report.

---

## 5. Component Deep Dive

### 5.1 The CLI (`cli.py`)
The CLI is the user-facing interface. It uses the **Typer** library to create a professional command-line interface.

**Key Features:**
- **Interactive Startup:** Helper prompts for configuring Host/Model.
- **Auto-Proxy:** Automatically handles `NO_PROXY` settings for seamless localhost connectivity.
- **Session Modes:** Supports `start`, `end`, `list`, and `chat` (REPL).

**Key Functions:**
- `run_command()`: The main entry point for user queries.
- `start_all_servers()`: Orchestrates the multi-process startup.

### 5.2 The Agent (`agent.py`)
The Agent is the central orchestrator. It coordinates communication between the CLI, LLM, and MCP servers.

**Key Functions:**
- `process_query()`: The main workflow function that processes a user query.
- `format_tool_result()`: Formats complex dictionaries (Pods, Services) into pretty CLI tables/lists.

### 5.3 DSPy Agent (`agent_module.py`)
The project uses **DSPy** (Declarative Self-improving Python) to orchestrate the LLM interactions.

**Key Components:**
- **FastAgent vs SmartAgent:**
    - **FastAgent:** Uses `dspy.Predict` (Zero-Shot) for speed (~1-2s).
    - **SmartAgent:** Uses `dspy.ChainOfThought` for complex reasoning (~5-8s).
- **Robust Parsing:** Includes a custom retry mechanism (`max_retries=2`) that feeds parsing errors back to the LLM to self-correct.

### 5.4 MCP Client (`mcp/client.py`)
The MCP client sends JSON-RPC 2.0 requests to the MCP servers.

### 5.5 MCP Servers
The project uses three separate MCP servers, each running on a different port:

#### Docker MCP Server (`mcp/server.py`)
- **Port:** 8080
- **Tools:** `docker_list_containers`, `docker_run_container`, `docker_stop_container`

#### Local Kubernetes MCP Server (`mcp/local_k8s_server.py`)
- **Port:** 8081
- **Tools:** `local_k8s_list_pods`, `local_k8s_list_nodes`

#### Remote Kubernetes MCP Server (`mcp/remote_k8s_server.py`)
- **Port:** 8082
- **Purpose:** Exposes Remote Kubernetes tools as JSON-RPC methods.
- **Tools:** 
    - `remote_k8s_list_pods`, `remote_k8s_list_nodes`
    - `remote_k8s_list_deployments`, `remote_k8s_describe_deployment`
    - `remote_k8s_list_namespaces`, `remote_k8s_describe_namespace`
    - `remote_k8s_find_pod_namespace`, `remote_k8s_get_resources_ips`
    - `remote_k8s_list_services`, `remote_k8s_get_service`, `remote_k8s_describe_service`
    - `remote_k8s_describe_pod`, `remote_k8s_describe_node`

**Server Architecture:**
Each server follows the same pattern:
1. **Import Tools:** Import the relevant tool classes.
2. **Create Handlers:** Use `create_tool_handler()` to wrap each tool.
3. **Register Methods:** Add each handler to the JSON-RPC dispatcher.
4. **Start Server:** Run the Werkzeug WSGI server.

### 5.6 Tools (`tools/` and `k8s_tools/`)
Tools are the actual implementations of Docker and Kubernetes operations. They follow a consistent interface defined by the `Tool` base class.

#### Tool Interface
```python
class Tool:
    name = "tool_name"
    description = "Human-readable description"
    
    def get_parameters_schema(self) -> dict:
        """Return JSON Schema for tool parameters"""
        pass
    
    def run(self, **kwargs) -> dict:
        """Execute the tool and return a structured result"""
        pass
```

### 5.7 Safety Layer (`safety.py`)
The safety layer prevents accidental destructive operations by requiring user confirmation.

**Key Functions:**
- `confirm_action()`: Prompts the user for confirmation before executing dangerous operations.
- `confirm_action_auto()`: Automatically selects the appropriate confirmation method.

### 5.8 Session Manager (`session_manager.py`)
The Session Manager handles conversation history, allowing the Agent to remember context (e.g., "describe *that* pod").

**Key Features:**
- **Persistence:** Saves sessions to local SQLite database (`agentic_docker/database/agentic_docker.db`).
- **Context Injection:** Feeds previous messages into the LLM prompt.
- **Management:** Create, list, delete, and resume sessions using SQL queries.

---

## 6. Multi-Server Architecture Benefits

The Multi-MCP architecture provides several key benefits:

### 6.1 Isolation
- **Separate Processes:** Each server runs in its own process, preventing one server's issues from affecting others.
- **Resource Management:** Each server can be monitored and managed independently.

### 6.2 Scalability
- **Independent Scaling:** You can run servers on different machines if needed.
- **Load Distribution:** Different domains (Docker, K8s) don't compete for the same server resources.

### 6.3 Maintainability
- **Clear Boundaries:** Each server has a specific responsibility, making code easier to understand and maintain.
- **Independent Development:** Teams can work on different servers without conflicts.

### 6.4 Reliability
- **Fault Tolerance:** If one server crashes, the others continue to work.
- **Graceful Degradation:** The system can still function with some servers down.

---

## 7. Command Chaining

The system supports **command chaining**, allowing multiple operations in a single query. This is achieved by having the LLM return a list of tool calls instead of a single call.

### Example: "Start nginx and list pods"
**User Query:** "Start nginx and list pods"

**LLM Response:**
```json
[
  {
    "name": "docker_run_container",
    "arguments": {
      "image": "nginx"
    }
  },
  {
    "name": "k8s_list_pods",
    "arguments": {
      "namespace": "default"
    }
  }
]
```

**Execution Flow:**
1. The Agent receives the list of tool calls.
2. For each tool call:
   - Apply safety checks.
   - Execute the tool via the appropriate MCP server.
   - Format the result.
3. Combine all results into a single response.

**Result:**
```
✅ Success! Container nginx started successfully.

🟢 nginx-abc123 (10.1.0.4) - Running [Ready: 1/1]
🟢 redis-master-xyz789 (10.1.0.5) - Running [Ready: 1/1]
```

---

## 8. Error Handling

The system includes comprehensive error handling at multiple levels:

### 8.1 LLM Errors
- **Connection Issues:** If Ollama is not running, the system provides a clear error message.
- **Model Issues:** If the model is not available, the system attempts to download it.
- **Parsing Errors:** If the LLM returns invalid JSON, the system handles it gracefully.

### 8.2 MCP Server Errors
- **Connection Issues:** If a server is not running, the system provides a helpful error message.
- **Timeout Errors:** If a server takes too long to respond, the system times out gracefully.
- **Tool Errors:** If a tool execution fails, the error is captured and returned to the user.

### 8.3 Tool Execution Errors
- **Validation Errors:** If tool arguments are invalid, Pydantic validation catches them.
- **Runtime Errors:** If a tool fails during execution, the error is captured and returned.
- **Permission Errors:** If Docker/Kubernetes permissions are insufficient, the error is clearly reported.

---

## 9. Configuration and Customization

The system can be configured through environment variables and configuration files.

### 9.1 Environment Variables
- `AGENTIC_DOCKER_HOST`: Host for MCP servers (default: 127.0.0.1)
- `AGENTIC_DOCKER_PORT`: Port for Docker MCP server (default: 8080)
- `AGENTIC_K8S_PORT`: Port for Local K8s MCP server (default: 8081)
- `AGENTIC_REMOTE_K8S_PORT`: Port for Remote K8s MCP server (default: 8082)
- `AGENTIC_LLM_MODEL`: LLM model to use (default: llama3.2)
- `AGENTIC_SAFETY_CONFIRM`: Enable/disable safety confirmation (default: true)

### 9.2 Adding New Tools
To add a new tool:

1. **Create the Tool Class:**
```python
class DockerLogsTool(Tool):
    name = "docker_get_logs"
    description = "Get logs from a running container"
    
    def get_parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "container_id": {
                    "type": "string",
                    "description": "ID or name of the container"
                }
            },
            "required": ["container_id"]
        }
    
    def run(self, **kwargs) -> dict:
        # Implementation
        pass
```

2. **Register the Tool:**
```python
# In tools/__init__.py
from .docker_logs import DockerLogsTool

ALL_TOOLS: List[Tool] = [
    DockerListContainersTool(),
    DockerRunContainerTool(),
    DockerStopContainerTool(),
    DockerLogsTool(),  # Add the new tool
]
```

3. **Restart the Server:** The new tool will be automatically registered with the MCP server.

---

## 10. Testing

The project includes a comprehensive test suite to ensure reliability.

### 10.1 Unit Tests
- **Tool Tests:** Test individual tool functionality.
- **LLM Tests:** Test LLM integration and tool selection.
- **Safety Tests:** Test safety confirmation logic.

### 10.2 Integration Tests
- **End-to-End Tests:** Test complete workflows from query to result.
- **Multi-Server Tests:** Test the interaction between different servers.
- **Error Handling Tests:** Test error scenarios and recovery.

### 10.3 Performance Tests
- **Tool Execution Time:** Measure how long tools take to execute.
- **LLM Response Time:** Measure LLM response times.
- **MCP Server Latency:** Measure server response times.

---

## 11. Future Enhancements

The project is designed to be extensible. Here are some potential future enhancements:

### 11.1 Additional Tool Categories
- **Image Management:** Pull, push, build, tag images.
- **Network Management:** Create, inspect, remove networks.
- **Volume Management:** Create, inspect, remove volumes.
- **Compose Support:** Manage Docker Compose applications.

### 11.2 Advanced LLM Features
- **Context Awareness:** Remember previous interactions for better responses.
- **Multi-Modal Input:** Support for images and other input types.
- **Custom Prompts:** Allow users to customize LLM prompts.

### 11.3 Enhanced Safety
- **Risk Assessment:** Automatically assess the risk level of operations.
- **Approval Workflows:** Require multiple approvals for high-risk operations.
- **Audit Logging:** Log all operations for compliance and debugging.

### 11.4 Performance Improvements
- **Caching:** Cache frequently used tool results.
- **Parallel Execution:** Execute independent tools in parallel.
- **Resource Monitoring:** Monitor system resources and adjust behavior accordingly.

---

## 12. Conclusion

The Agentic Docker project demonstrates a sophisticated approach to AI-powered DevOps tooling. By combining local LLMs, the Model Context Protocol, and a multi-server architecture, it provides a powerful and flexible platform for managing Docker and Kubernetes clusters using natural language.

The architecture is designed to be:
- **Reliable:** Through comprehensive error handling and testing.
- **Extensible:** Through a modular tool system and clear interfaces.
- **Safe:** Through safety checks and confirmation prompts.
- **Scalable:** Through a multi-server architecture that can grow with needs.

Whether you're a developer looking to simplify your workflow or an organization looking to build AI-powered DevOps tools, the Agentic Docker project provides a solid foundation for building intelligent, user-friendly systems.