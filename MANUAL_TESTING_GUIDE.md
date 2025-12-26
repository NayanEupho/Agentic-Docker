# Manual Testing Guide: DevOps Agent

This guide provides a comprehensive checklist for validating the **DevOps Agent** across both the **CLI** and the **Next.js Web UI**. It covers all core features, including the new **RAG / Embedding Engine**, **Smart Routing**, and **Thinking UI**.

---

## 🛠️ Prerequisites & Setup

Ensure your environment is ready before running tests.

1.  **Start Ollama:**
    ```bash
    ollama serve
    ```
2.  **Start System (Wizard/All Servers):**
    ```bash
    devops-agent start-all
    ```
    *Follow the wizard to select Models (Smart/Fast) and Embedding Model.*

3.  **Start Web UI (Optional for CLI tests, Required for Part 2):**
    ```bash
    cd ui && npm run dev
    ```

---

## 💻 Part 1: CLI Application Testing

Verify the core logic and terminal interface.

### 1.1 RAG & Embeddings (New!)
The agent now uses a local FAISS vector index (`nomic-embed-text`) to find relevant tools.

| Command | Description | Expected Output |
| :--- | :--- | :--- |
| `devops-agent rag list` | List all indexed tools. | Table with columns: `ID`, `Name`, `Description`. Should show ~50+ tools. |
| `devops-agent rag info <tool_name>` | Check specific embedding. | Example: `devops-agent rag info docker_run_container`. Output: `[0.123, -0.45, ...]`. |
| `devops-agent rag verify` | Health check for index. | JSON Output: `{"valid": true, "tool_count": 52, ...}`. |
| `devops-agent rag rebuild` | Force re-indexing. | `[Success] Index rebuilt with 52 tools.` |

### 1.2 Session Management
Test persistence of context.

1.  **Start a new session:**
    ```bash
    devops-agent session start "Testing RAG"
    ```
    *Output: `Session started: <uuid>`*
2.  **Run a command:**
    ```bash
    devops-agent run "List my docker containers"
    ```
3.  **List sessions:**
    ```bash
    devops-agent session list
    ```
    *Verify "Testing RAG" appears.*
4.  **Show history:**
    ```bash
    devops-agent session show <session_id>
    ```
    *Verify the previous command and output are listed.*
5.  **Clear/End:**
    ```bash
    devops-agent session end
    devops-agent session clear
    ```

### 1.3 Chat Mode (Interactive REPL)
1.  Run `devops-agent chat`.
2.  Type: `List local pods`. -> *Should run tool.*
3.  Type: `System status`. -> *Should show active models.*
4.  Type: `/bye` or `/exit`. -> *Should exit cleanly.*

### 1.4 Smart vs Fast Mode
1.  **Fast Path (Simple):**
    ```bash
    devops-agent run "docker ps"
    ```
    *Observability: Should be instant (<2s). Log should imply "Fast Path" or "Zero-Shot".*

2.  **Smart Path (Reasoning):**
    ```bash
    devops-agent run "Find the pod with the highest restart count in kube-system and describe it"
    ```
    *Observability: Should take longer. Log should show "Thinking..." steps.*

---

## 🖥️ Part 2: GUI Testing (Next.js Web Interface)

Verify the UX, real-time streaming, and visual feedback. (**URL:** `http://localhost:3000`)

### 2.1 The "Thinking" UI (DeepSeek Style)
1.  **Trace:** Submit a complex query: *"Analyze the logs of the nginx container and tell me why it failed."*
2.  **Verify:**
    *   [ ] A "Thinking..." accordion appears immediately.
    *   [ ] It expands to show steps: `Checking Docker...`, `Reading Logs...`.
    *   [ ] A Step Counter (`Step 1/5`) and Timer (`1.2s`) are visible.
    *   [ ] When finished, the section **auto-collapses**.
    *   [ ] Clicking the header re-expands it.

### 2.2 RAG Attribution & Tool Chips
1.  **Trace:** Ask: *"Start an nginx container."*
2.  **Verify:**
    *   [ ] A "Tool Used" chip (`🛠️ docker_run_container`) appears in the chat stream.
    *   [ ] Hovering/Clicking it shows the JSON arguments used (`{ "image": "nginx" }`).

### 2.3 Configuration Modal (Hot-Swapping)
1.  **Action:** Click the "Settings" (Gear) icon in sidebar.
2.  **Test:**
    *   Change "Smart Model" from `qwen2.5:72b` to `llama3.2`.
    *   Click "Save".
3.  **Verify:**
    *   Submit a query. Verify in terminal logs that `llama3.2` is now being invoked.

### 2.4 Safety & Approval Cards ("Human-in-the-Loop")
1.  **Action:** Submit a destructive command: *"Delete the container named 'mongo-prod'".*
2.  **Verify:**
    *   [ ] Chat stream pauses.
    *   [ ] A **Glassmorphic Decision Card** appears with "Approve" (Green) and "Deny" (Red) buttons.
    *   [ ] Risk Level "HIGH" and Reason "Destructive Action" are displayed.
3.  **Branch A (Deny):** Click "Deny".
    *   [ ] Chat shows "Action Cancelled by User".
    *   [ ] Container is **not** deleted.
4.  **Branch B (Approve):** Click "Approve".
    *   [ ] Loading spinner appears.
    *   [ ] "Container Deleted" message appears.

### 2.5 Sidebar & System Status
1.  **Status Indicators:**
    *   Check the bottom left of the sidebar.
    *   [ ] **AI Models:** Green dot if Ollama is up.
    *   [ ] **Docker/K8s:** Green dot if MCP servers are connected.
2.  **Session Switching:**
    *   Create 2-3 new chats.
    *   Click between them in the sidebar.
    *   Verify message history loads instantly for each.

---

## 🚀 Part 3: End-to-End Scenarios

### Scenario A: The "Sticky Context" (Remote K8s)
1.  **Command 1:** *"List pods in the remote cluster."*
    *   *Result:* Lists pods from `remote_k8s_server`.
2.  **Command 2:** *"Describe the first one."*
    *   *Result:* Agent intelligently picks `remote_k8s_describe_pod` (NOT local) because of previous context.

### Scenario B: The "RAG Stress Test"
1.  **Command:** *"Check the taints on node 'worker-1' in the remote cluster."*
    *   *Mechanism:*
        *   User query -> Embedding -> FAISS Search.
        *   FAISS should return `remote_k8s_get_node` (or describe).
        *   LLM calls tool -> Output parses taints.
    *   *Failure Mode:* If it says "I don't know how", RAG failed to retrieve the tool. Run `devops-agent rag info remote_k8s_describe_node` to investigate.

### Scenario C: Error Self-Correction
1.  **Command:** *"Get logs for pod 'non-existent-pod'."*
    *   *Expected:* Tool returns error. Agent sees error.
    *   *Output:* Agent explains: *"I couldn't finding that pod. Are you sure it's in the default namespace?"* (Instead of crashing).

### Scenario D: Command Chaining (Multi-Step)
1.  **Command:** *"Start an nginx container and then list all running containers."*
    *   *Mechanism:*
        *   LLM generates 2 tool calls: `docker_run_container` AND `docker_list_containers`.
        *   Agent runs them (often in parallel/sequence depending on order).
    *   *Verification:*
        *   [ ] Output includes "Container started" result.
        *   [ ] Output includes the Table of containers.
        *   [ ] Verify the new nginx container appears in that table.

2.  **Command:** *"List nodes and pods in remote cluster."*
    *   *Verification:*
        *   [ ] Output displays TWO distinct tables (Nodes and Pods).

### Scenario E: Large Dataset Handling & Filtering (High Perf)
1. **Zero-Latency Smart Match:**
   - **Command:** `list pending pods in kube-system`
   - *Verify:* Response should be **instant** (<100ms in logs). No "Thinking..." accordion should appear (bypassed LLM).
2. **Smart Summarization:**
   - **Command:** `list all pods` (in a large cluster).
   - *Verify:* The result should start with a **Summary** (e.g., `Running: 45 | Pending: 5`).
3. **Adaptive Truncation:**
   - **Command:** `list pods` (when count > 25).
   - *Verify:* The table should show exactly 20-25 items followed by a `> [!NOTE]` explaining how to filter further.
4. **Server-Side Filter:**
   - **Command:** `list pods labeled app=nginx`
   - *Verify:* The result table should only contain nginx pods. Check terminal logs to verify `label_selector` was passed to the MCP tool.

### Scenario F: Batch Describe Parallel Execution (New!)
1. **Zero-Latency Batch Routing:**
   - **Command:** `describe all pending pods`
   - *Verify:* Console log shows `⚡ [RegexRouter] Batch Describe:`; no LLM call. Response shows table with status/events/conditions.
2. **Full Detail Mode:**
   - **Command:** `describe every running deployment with full details`
   - *Verify:* Output shows YAML blocks for each deployment instead of table.
3. **Parallel Execution:**
   - **Command:** `describe all nodes`
   - *Verify:* Console log shows `🚀 [BatchDescribe] Parallel execution: N x remote_k8s_describe_node`. All nodes described in single response.
4. **Namespace Filter:**
   - **Command:** `describe all pods in kube-system`
   - *Verify:* Only pods from kube-system namespace are described.

---

## 🛑 Troubleshooting Common Failures

| Symptom | Check | Fix |
| :--- | :--- | :--- |
| **"Connection Refused"** | Is `ollama serve` running? | Run `ollama serve` in a new terminal. |
| **"Tool not found"** | Did you start the MCP servers? | Run `devops-agent start-all`. |
| **"UI is stuck / no stream"** | Is the API server up? | Check terminal running `start-all`. Ensure port 8088 is free. |
| **"RAG returns nothing"** | Verify index. | Run `devops-agent rag verify`. If 0 tools, run `rebuild`. |
