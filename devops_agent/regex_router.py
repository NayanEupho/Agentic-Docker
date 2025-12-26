import re
from typing import Optional, List, Dict, Any

class RegexRouter:
    """
    Enhanced router for instant command matching and parameter extraction.
    Bypasses LLM for standard, high-frequency commands with zero latency.
    """
    
    # Pre-compiled status phases for fast matching
    PHASES_LIST = r"running|pending|failed|succeeded|unknown|paused"
    PHASES = rf"(?P<status_phase>{PHASES_LIST})"
    
    # Patterns with named capture groups for automatic parameter extraction
    PATTERNS = [
        # --- [BATCH DESCRIBE] High-Priority Pattern for "describe all X" ---
        # Captures: describe (all/every) (status) (pods/deployments/services/nodes)
        (re.compile(rf"describe\s+(?P<batch_all>all(?:\s+the)?|every)\s+(?P<batch_status>{PHASES_LIST})?\s*(?P<batch_remote>remote\s+)?(?P<batch_resource>pods?|deployments?|services?|nodes?)((?:\s+with\s+|\s+)(?P<batch_detail>full\s+details?|all\s+(?:the\s+)?details?|every\s+details?|verbose|detailed))?(\s+in\s+(?P<batch_ns>[\w-]+))?", re.I), "batch_describe"),
        
        # --- Pods/Deployments/Services (Local/Remote/Namespace/Status) ---
        (re.compile(rf"(list|get|show|describe)\s+(all\s+the\s+|all\s+)?(?P<remote>remote\s+)?({PHASES}\s+)?(?P<resource_type_list>pods|deployments|services|namespaces)(\s+that\s+are\s+(?P<status_phase_alt>{PHASES_LIST}))?(\s+in\s+(?P<namespace>[\w-]+))?", re.I), "list_resources"),
        
        # --- Single Resource Detail ---
        (re.compile(rf"(get|describe|show)\s+(?P<remote_detail>remote\s+)?(?P<res_type_detail>pod|deployment|service|namespace)\s+(?P<res_name_detail>[\w-]+)(\s+in\s+(?P<ns_detail>[\w-]+))?", re.I), "describe_resource"),

        # --- Pod Logs ---
        (re.compile(rf"(get|show|view|read)\s+(the\s+)?logs?\s+(for|of\s+)?(?P<remote_logs>remote\s+)?(?P<pod_name_logs>[\w-]+)(\s+in\s+(?P<ns_logs>[\w-]+))?", re.I), "get_logs"),

        # --- Nodes ---
        (re.compile(rf"(list|get|show)\s+(?P<remote>remote\s+)?nodes", re.I), "list_nodes"),
        
        # --- Docker ---
        (re.compile(r"((docker\s+)?ps|list\s+containers)", re.I), "docker_list_containers"),
        (re.compile(r"docker\s+(stop|start|restart)\s+(?P<container_name_or_id>[\w-]+)", re.I), "docker_{status}"), # status will be mapped
        (re.compile(r"docker\s+logs\s+(?P<container_name_or_id>[\w-]+)", re.I), "docker_get_container_logs"),
        (re.compile(r"docker\s+inspect\s+(?P<container_name_or_id>[\w-]+)", re.I), "docker_get_container_details"),
        (re.compile(r"(stop|terminate)\s+(all\s+)?containers", re.I), "docker_stop_all_containers"),
        
        # --- Promotion ---
        (re.compile(r"promote\s+(?P<resource_type>pod|deployment|service|configmap|secret)\s+(?P<name>[\w-]+)(\s+from\s+local)?(\s+to\s+remote)?", re.I), "promote_resource"),
        
        # --- [PHASE 4] Advanced Orchestration & Diagnostics ---
        # Tracer: "trace pod web-app", "why is pod web-app crashing", "diagnose web-app"
        (re.compile(r"(trace|diagnose|troubleshoot|why\s+is|what's\s+wrong\s+with)\s+(all\s+the\s+)?(pod\s+|deployment\s+)?(?P<pod_name_trace>[\w-]+)(\s+(is\s+)?crashing|failing|error)?(\s+in\s+(namespace\s+)?(?P<namespace_trace>[\w-]+))?", re.I), "trace_dependencies"),
        
        # Events: "show events for web-app"
        (re.compile(r"(show|list|get)\s+(the\s+)?events\s+(for\s+)?(?P<pod_name_events>[\w-]+)(\s+in\s+(namespace\s+)?(?P<namespace_events>[\w-]+))?", re.I), "list_events"),

        # Discovery: "find namespace for auth-db"
        (re.compile(r"find\s+(?P<find_ns>namespace|ns|location)\s+(for\s+|of\s+)?(?P<resource_name_find>[\w-]+)", re.I), "find_ns"),
        
        # Diff: "compare deployment web-app"
        (re.compile(r"(compare|diff)\s+(?P<res_type_diff>pod|deployment|service)\s+(?P<res_name_diff>[\w-]+)(\s+in\s+(namespace\s+)?(?P<ns_diff>[\w-]+))?", re.I), "diff_resources"),
        
        # Analysis: "analyze utilization in prod"
        (re.compile(r"(analyze\s+)?utilization(\s+in\s+(namespace\s+)?(?P<ns_util>[\w-]+))?", re.I), "analyze_utilization")
    ]

    @staticmethod
    def route(query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Try to match a query to a tool call using smart regex extraction.
        Returns None if no match found.
        """
        q = query.strip()
        
        for pattern, base_name in RegexRouter.PATTERNS:
            match = pattern.fullmatch(q)
            if match:
                extracted = match.groupdict()
                
                # 1. Determine Provider (remote_k8s_ vs local_k8s_ vs docker_)
                if base_name.startswith("docker"):
                    tool_name = base_name
                    # Handle dynamic tool names like docker_{status}
                    if "{status}" in tool_name and match.lastindex >= 1:
                        action = match.group(1).lower()
                        tool_name = tool_name.format(status=action)
                elif base_name == "list_resources":
                    rtype = extracted.get("resource_type_list", "pods").lower()
                    prefix = "remote_k8s_" if extracted.get("remote") else "local_k8s_"
                    tool_name = f"{prefix}list_{rtype}"
                    
                elif base_name == "batch_describe":
                    # --- BATCH DESCRIBE ORCHESTRATION ---
                    # Returns a list tool call with metadata for agent post-processing
                    rtype_raw = extracted.get("batch_resource", "pods").lower()
                    # Normalize to plural
                    rtype = rtype_raw if rtype_raw.endswith("s") else f"{rtype_raw}s"
                    
                    prefix = "remote_k8s_" if extracted.get("batch_remote") else "local_k8s_"
                    list_tool = f"{prefix}list_{rtype}"
                    
                    args = {"limit": 100}  # High limit for batch
                    
                    # Status filter
                    if extracted.get("batch_status"):
                        args["status_phase"] = extracted["batch_status"].capitalize()
                    
                    # Namespace
                    if extracted.get("batch_ns"):
                        args["namespace"] = extracted["batch_ns"]
                    elif rtype in ["pods", "deployments", "services"]:
                        args["namespace"] = "default"
                    
                    # Detect detail level
                    full_detail = bool(extracted.get("batch_detail"))
                    
                    # Return with batch metadata for agent post-processor
                    print(f"⚡ [RegexRouter] Batch Describe: '{query}' -> {list_tool}({args}) [detail={full_detail}]")
                    return [{
                        "name": list_tool,
                        "arguments": args,
                        "_batch_describe": True,
                        "_batch_resource_type": rtype_raw.rstrip("s"),  # Singular for describe tool
                        "_batch_full_detail": full_detail,
                        "_batch_prefix": prefix
                    }]
                    
                elif base_name == "describe_resource":
                    rtype = extracted.get("res_type_detail", "pod").lower()
                    prefix = "remote_k8s_" if extracted.get("remote_detail") else "local_k8s_"
                    tool_name = f"{prefix}describe_{rtype}"
                    if rtype == "service": tool_name = tool_name.replace("describe", "get") # Tool naming inconsistency fix
                elif base_name == "get_logs":
                    prefix = "remote_k8s_" if extracted.get("remote_logs") else "local_k8s_"
                    tool_name = f"{prefix}get_pod_logs"
                elif base_name == "promote_resource":
                    tool_name = "remote_k8s_promote_resource"
                elif base_name == "find_ns":
                    tool_name = "remote_k8s_find_resource_namespace"
                elif base_name == "trace_dependencies":
                    tool_name = "remote_k8s_trace_dependencies"
                elif base_name == "list_events":
                    tool_name = "remote_k8s_list_events"
                elif base_name == "diff_resources":
                    tool_name = "remote_k8s_diff_resources"
                elif base_name == "analyze_utilization":
                    tool_name = "remote_k8s_analyze_utilization"
                else:
                    prefix = "remote_k8s_" if extracted.get("remote") else "local_k8s_"
                    tool_name = f"{prefix}{base_name}"

                # 2. Build Arguments
                args = {}
                
                # Namespace
                if extracted.get("namespace"):
                    args["namespace"] = extracted["namespace"]
                elif extracted.get("namespace_trace"):
                    args["namespace"] = extracted["namespace_trace"]
                elif extracted.get("ns_diff"):
                    args["namespace"] = extracted["ns_diff"]
                elif extracted.get("namespace_util"):
                    args["namespace"] = extracted["namespace_util"]
                elif extracted.get("namespace_events"):
                    args["namespace"] = extracted["namespace_events"]
                elif extracted.get("ns_detail"):
                    args["namespace"] = extracted["ns_detail"]
                elif extracted.get("ns_logs"):
                    args["namespace"] = extracted["ns_logs"]
                elif any(x in tool_name for x in ["pods", "deployments", "services", "trace", "diff", "analyze", "events"]):
                    args["namespace"] = "default"
                
                # Names for Describe/Logs
                if extracted.get("res_name_detail"):
                    args["name"] = extracted["res_name_detail"]
                if extracted.get("pod_name_logs"):
                    args["pod_name"] = extracted["pod_name_logs"]
                
                # Resource Type for Diff
                if extracted.get("res_type_diff"):
                    # Map to plural for the tool
                    mapping = {"pod": "pods", "deployment": "deployments", "service": "services"}
                    args["resource_type"] = mapping.get(extracted["res_type_diff"].lower(), "pods")
                
                # Resource Names
                if extracted.get("resource_name_find"):
                    args["name"] = extracted["resource_name_find"]
                if extracted.get("pod_name_trace"):
                    args["pod_name"] = extracted["pod_name_trace"]
                if extracted.get("pod_name_events"):
                    args["pod_name"] = extracted["pod_name_events"]
                if extracted.get("res_name_diff"):
                    args["resource_name"] = extracted["res_name_diff"]
                
                # Default for utilization
                if "analyze_utilization" in tool_name:
                    args["risk_threshold"] = 90

                # Container ID/Name
                if extracted.get("container_name_or_id"):
                    args["container_name_or_id"] = extracted["container_name_or_id"]

                # Promotion args
                if extracted.get("resource_type"):
                    args["resource_type"] = extracted["resource_type"]
                if extracted.get("name"):
                    args["name"] = extracted["name"]
                    
                # Status Phase
                phase_raw = extracted.get("status_phase") or extracted.get("status_phase_alt")
                if phase_raw:
                    phase = phase_raw.lower()
                    if phase == "paused":
                        # K8s doesn't have a 'Paused' phase, so we list all and let LLM find non-running ones
                        pass
                    else:
                        # K8s API expects capitalized phases (Running, Pending)
                        args["status_phase"] = phase.capitalize()
                
                # Default Performance Limit
                if any(x in tool_name for x in ["list", "ps"]):
                    args["limit"] = 50

                print(f"⚡ [RegexRouter] Smart Match: '{query}' -> {tool_name}({args})")
                return [{"name": tool_name, "arguments": args}]
                
        return None
