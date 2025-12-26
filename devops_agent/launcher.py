import os
import sys
import json
import time
import signal
import subprocess
import atexit
from typing import Dict, Optional

LOCK_FILE = ".agent.lock"

class AgentLauncher:
    """
    Supervisor for DevOps Agent processes.
    Ensures single instance via PID lockfile and handles graceful shutdown.
    """
    
    def __init__(self):
        self.pids: Dict[str, int] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        
    def _is_pid_alive(self, pid: int) -> bool:
        """Check if a PID is alive using os.kill(pid, 0)."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
            
    def check_lock(self):
        """Check if lock file exists and if processes are actually running."""
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    data = json.load(f)
                    
                # Verify if main PID is alive
                main_pid = data.get("main_pid")
                if main_pid and self._is_pid_alive(main_pid):
                    print(f"❌ Agent is already running (PID {main_pid}).")
                    print("   Run 'devops-agent stop-all' or kill the existing process.")
                    sys.exit(1)
                else:
                    print("⚠️  Found stale lockfile. Cleaning up...")
                    self.cleanup_lock()
            except Exception as e:
                print(f"⚠️  Corrupt lockfile ({e}). Cleaning up...")
                self.cleanup_lock()

    def cleanup_lock(self):
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass

    def start_all(self):
        self.check_lock()
        self.running = True
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)
        atexit.register(self.handle_exit)
        
        print("🚀 Starting DevOps Agent Stack (Supervisor Mode)")
        
        base_cmd = [sys.executable, "-m", "devops_agent.cli"]
        flag = 0
        if sys.platform == "win32":
            flag = subprocess.CREATE_NEW_CONSOLE

        try:
            # 1. API Server
            print("   • Launching API Server (8088)...")
            self.spawn("api", [sys.executable, "-m", "devops_agent.api_server"], flag)
            
            # 2. Docker MCP
            print("   • Launching Docker MCP (8080)...")
            self.spawn("docker", base_cmd + ["server", "--port", "8080"], flag)
            
            # 3. K8s Local MCP
            print("   • Launching Local K8s MCP (8081)...")
            self.spawn("k8s_local", base_cmd + ["k8s-server", "--port", "8081"], flag)
            
            # 4. K8s Remote MCP
            print("   • Launching Remote K8s MCP (8082)...")
            self.spawn("k8s_remote", base_cmd + ["remote-k8s-server", "--port", "8082"], flag)
            
            # Write lockfile
            self.write_lock()
            print("\n✨ Stack is running. Press Ctrl+C to stop ALL servers.")
            
            # Monitor loop
            while self.running:
                time.sleep(1)
                # Check for unexpected deaths
                for name, p in list(self.processes.items()):
                    if p.poll() is not None:
                        print(f"⚠️  Process {name} died (Exit Code: {p.returncode}). Restarting...")
                        # Simple restart logic could go here, but for now just warn
                        del self.processes[name]
                
                if not self.processes:
                     print("❌ All subprocesses died. Exiting.")
                     break
                     
        except KeyboardInterrupt:
            self.handle_exit()

    def spawn(self, name: str, cmd: list, flags: int):
        p = subprocess.Popen(cmd, creationflags=flags)
        self.processes[name] = p
        self.pids[name] = p.pid

    def write_lock(self):
        data = {
            "main_pid": os.getpid(),
            "children": self.pids
        }
        with open(LOCK_FILE, 'w') as f:
            json.dump(data, f)
            
    def handle_exit(self, signum=None, frame=None):
        if not self.running: return
        self.running = False
        
        print("\n🛑 Stopping all servers...")
        self.cleanup_lock()
        
        for name, p in self.processes.items():
            if p.poll() is None:
                print(f"   • Terminating {name} (PID {p.pid})...")
                p.terminate()
                # p.kill() # If needed
        
        print("✅ Shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    launcher = AgentLauncher()
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        launcher.start_all()
