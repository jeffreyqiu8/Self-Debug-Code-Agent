"""Sandbox execution backends for running code in isolated environments."""

import subprocess
import sys
import tempfile
import os
import traceback
from typing import Protocol, runtime_checkable

from models import ExecutionResult


@runtime_checkable
class SandboxExecutor(Protocol):
    """Protocol defining the interface for sandbox execution backends."""

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult: ...


class SubprocessSandbox:
    """Execute code via subprocess.run() with restricted permissions."""

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Run code in a subprocess with restricted permissions.

        Creates a temporary file with the code, executes it in a subprocess
        with restricted environment variables, and captures all output.
        """
        tmp_file = None
        try:
            # Write code to a temporary file
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            )
            tmp_file.write(code)
            tmp_file.close()

            # Build restricted environment: only essential vars
            restricted_env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONPATH": "",
                "HOME": tempfile.gettempdir(),
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            try:
                result = subprocess.run(
                    [sys.executable, "-u", tmp_file.name],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=restricted_env,
                    cwd=tempfile.gettempdir(),
                )
            except subprocess.TimeoutExpired as e:
                return ExecutionResult(
                    stdout=e.stdout or "" if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", errors="replace") if e.stdout else ""),
                    stderr=e.stderr or "" if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", errors="replace") if e.stderr else ""),
                    exit_code=-1,
                    exception_trace=f"TimeoutError: Code execution exceeded {timeout} seconds",
                    timed_out=True,
                )

            # Extract exception trace from stderr if exit code is non-zero
            exception_trace = None
            if result.returncode != 0 and result.stderr:
                exception_trace = _extract_traceback(result.stderr)

            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                exception_trace=exception_trace,
                timed_out=False,
            )

        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                exception_trace=traceback.format_exc(),
                timed_out=False,
            )
        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)


class DockerSandbox:
    """Execute code in a Docker container via the docker SDK."""

    def __init__(self, image: str = "python:3.12-slim") -> None:
        self.image = image
        self._client = None

    @property
    def client(self):
        """Lazy-initialize the Docker client."""
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Run code in a Docker container with isolation.

        Uses the docker SDK to run code in a container with:
        - No network access
        - Read-only root filesystem (with a tmpfs for /tmp)
        - Memory limits
        - Automatic removal after execution
        """
        try:
            import docker
            from docker.errors import ContainerError, ImageNotFound, APIError
        except ImportError:
            return ExecutionResult(
                stdout="",
                stderr="docker package is not installed. Install with: pip install docker",
                exit_code=-1,
                exception_trace="ImportError: No module named 'docker'",
                timed_out=False,
            )

        try:
            container = self.client.containers.run(
                image=self.image,
                command=["python", "-u", "-c", code],
                detach=True,
                network_disabled=True,
                read_only=True,
                tmpfs={"/tmp": "size=64M"},
                mem_limit="128m",
                pids_limit=64,
                stderr=True,
                stdout=True,
            )

            try:
                result = container.wait(timeout=timeout)
            except Exception:
                # Timeout or other wait error — kill and flag as timed out
                try:
                    container.kill()
                except Exception:
                    pass
                stdout_log = container.logs(stdout=True, stderr=False).decode(
                    "utf-8", errors="replace"
                )
                stderr_log = container.logs(stdout=False, stderr=True).decode(
                    "utf-8", errors="replace"
                )
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                return ExecutionResult(
                    stdout=stdout_log,
                    stderr=stderr_log,
                    exit_code=-1,
                    exception_trace=f"TimeoutError: Code execution exceeded {timeout} seconds",
                    timed_out=True,
                )

            # Collect output
            stdout_log = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr_log = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )
            exit_code = result.get("StatusCode", -1)

            # Extract exception trace from stderr if non-zero exit
            exception_trace = None
            if exit_code != 0 and stderr_log:
                exception_trace = _extract_traceback(stderr_log)

            try:
                container.remove(force=True)
            except Exception:
                pass

            return ExecutionResult(
                stdout=stdout_log,
                stderr=stderr_log,
                exit_code=exit_code,
                exception_trace=exception_trace,
                timed_out=False,
            )

        except ImageNotFound:
            return ExecutionResult(
                stdout="",
                stderr=f"Docker image '{self.image}' not found. Pull it with: docker pull {self.image}",
                exit_code=-1,
                exception_trace=f"ImageNotFound: {self.image}",
                timed_out=False,
            )
        except APIError as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Docker API error: {e.explanation}",
                exit_code=-1,
                exception_trace=str(e),
                timed_out=False,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                exception_trace=traceback.format_exc(),
                timed_out=False,
            )


def _extract_traceback(stderr: str) -> str | None:
    """Extract the traceback portion from stderr output.

    Looks for 'Traceback (most recent call last)' and returns everything
    from that point onward. Returns the full stderr if no traceback marker
    is found but stderr is non-empty.
    """
    if not stderr:
        return None
    marker = "Traceback (most recent call last)"
    idx = stderr.find(marker)
    if idx != -1:
        return stderr[idx:].strip()
    return stderr.strip()
