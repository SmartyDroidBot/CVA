"""Docker sandbox for safe script execution."""

from typing import Optional


class Sandbox:
    """Docker-based sandbox for executing untrusted scripts."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._client = None
    
    def _get_client(self):
        """Lazy-load Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except Exception as e:
                raise RuntimeError(f"Docker not available: {e}")
        return self._client
    
    def execute(self, script: str, language: str = "python", 
                network: bool = False, timeout: int = 60,
                mem_limit: str = "256m") -> str:
        """
        Execute a script in a Docker container.
        
        Args:
            script: Script content to execute
            language: 'python' or 'bash'
            network: Allow network access (default: False for safety)
            timeout: Execution timeout in seconds
            mem_limit: Container memory limit
        
        Returns:
            Script output or error message
        """
        if not self.enabled:
            return "Sandbox is disabled. Enable it in settings."
        
        try:
            client = self._get_client()
            
            image = "python:3.12-slim" if language == "python" else "bash:latest"
            cmd = ["python", "-c", script] if language == "python" else ["bash", "-c", script]
            
            container_output = client.containers.run(
                image=image,
                command=cmd,
                detach=False,
                remove=True,
                network_mode="bridge" if network else "none",
                mem_limit=mem_limit,
                cpu_period=100000,
                cpu_quota=50000,  # 50% of one CPU
                stdout=True,
                stderr=True,
            )
            
            return container_output.decode("utf-8") if isinstance(container_output, bytes) else str(container_output)
            
        except Exception as e:
            return f"Sandbox execution error: {e}"
    
    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            self._get_client()
            return True
        except Exception:
            return False
