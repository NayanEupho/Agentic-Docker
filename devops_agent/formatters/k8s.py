# devops_agent/formatters/k8s.py
from typing import Dict, Any
from .base import BaseFormatter
from collections import Counter

class KubernetesFormatter(BaseFormatter):
    def can_format(self, tool_name: str) -> bool:
        return "k8s_" in tool_name

    def format(self, tool_name: str, result: Dict[str, Any]) -> str:
        if "list_pods" in tool_name:
             pods = result.get("pods", [])
             ns = result.get("namespace", "unknown")
             scope = "REMOTE" if "remote" in tool_name else "LOCAL"
             if not pods: return f"✅ Success! No pods in '{ns}' ({scope})."

             status_counts = Counter([p.get('phase', 'Unknown') for p in pods])
             summary = ", ".join([f"{k}: {v}" for k, v in status_counts.items()])

             headers = ["Status", "Name", "Restarts", "Age", "Node"]
             rows = []
             for p in pods:
                 status = p.get('phase', 'Unknown')
                 emoji = "🟢" if status == "Running" else "🟡" if status == "Pending" else "🔴"
                 rows.append([
                     f"{emoji} {status}",
                     p['name'],
                     p.get('restarts', 0),
                     p.get('age', '?'),
                     p.get('node', '?')
                 ])
             return f"✅ **Kubernetes Pods in '{ns}' ({scope})**\n*Summary: {summary}*\n\n" + self._to_markdown_table(headers, rows)

        elif "list_nodes" in tool_name:
             nodes = result.get("nodes", [])
             scope = "REMOTE" if "remote" in tool_name else "LOCAL"
             
             if not nodes: return f"✅ No nodes found ({scope})."
             
             # Summary
             status_counts = Counter([n.get('status', 'Unknown') for n in nodes])
             summary = ", ".join([f"{k}: {v}" for k, v in status_counts.items()])
             
             headers = ["Status", "Name", "Roles", "Version", "Internal-IP"]
             rows = []
             for n in nodes:
                 status = n.get('status', 'Unknown')
                 emoji = "🟢" if "Ready" in status else "🔴"
                 
                 rows.append([
                     f"{emoji} {status}",
                     n['name'],
                     ", ".join(n.get('roles', [])),
                     n.get('kubelet_version', '?'),
                     n.get('internal_ip') or n.get('ip', '?')
                 ])
             return f"✅ **Kubernetes Nodes ({scope})**\n*Summary: {summary}*\n\n" + self._to_markdown_table(headers, rows)

        elif "describe_pod" in tool_name or "describe_deployment" in tool_name or "describe_node" in tool_name:
            # High-intelligence formatting for complex strings
            data = result.get("data", str(result))
            if isinstance(data, str) and "Name:" in data:
                return f"📋 **Detailed Description**:\n```yaml\n{data}\n```"
            return f"✅ **Resource Details**:\n{data}"

        # [BATCH DESCRIBE] Aggregated output for parallel describes
        elif result.get("_batch"):
            resources = result.get("resources", [])
            resource_type = result.get("resource_type", "resource")
            full_detail = result.get("_full_detail", False)
            
            if not resources:
                return f"✅ No {resource_type}s to describe."
            
            if full_detail:
                # Full detail view - YAML blocks for each resource
                output = f"📋 **Batch Describe: {len(resources)} {resource_type}s (Full Detail)**\n\n"
                for r in resources:
                    output += f"---\n### {r['name']} ({r.get('status', 'Unknown')})\n"
                    if r.get("error"):
                        output += f"⚠️ Error: {r['error']}\n"
                    elif r.get("details"):
                        details = r["details"]
                        if isinstance(details, str):
                            output += f"```yaml\n{details[:2000]}\n```\n"
                        else:
                            import json
                            output += f"```json\n{json.dumps(details, indent=2)[:2000]}\n```\n"
                return output.strip()
            else:
                # Compact summary view - Table format
                output = f"📋 **Batch Describe: {len(resources)} {resource_type}s**\n\n"
                
                # Status summary
                status_counts = Counter([r.get('status', 'Unknown') for r in resources])
                summary = ", ".join([f"{k}: {v}" for k, v in status_counts.items()])
                output += f"*Summary: {summary}*\n\n"
                
                # Table
                headers = ["Status", "Name", "Events", "Conditions"]
                rows = []
                for r in resources:
                    status = r.get("status", "Unknown")
                    emoji = "🟢" if status == "Running" or "Ready" in status else "🟡" if status == "Pending" else "🔴"
                    
                    if r.get("error"):
                        rows.append([f"❌ Error", r["name"], r["error"][:40], "-"])
                    else:
                        rows.append([
                            f"{emoji} {status}",
                            r["name"],
                            r.get("events", "No events")[:40],
                            r.get("conditions", "Unknown")[:30]
                        ])
                
                output += self._to_markdown_table(headers, rows)
                return output

        return f"✅ K8s Tool '{tool_name}' executed successfully."
