"""Sandbox for safe code execution.

Provides two isolation levels:
1. bwrap (bubblewrap) — full filesystem/network isolation (when available)
2. Python resource limits — CPU/memory/file limits (always available)

Falls back gracefully: bwrap → resource limits → plain execution with timeout.
"""

from __future__ import annotations

import logging
import os
import resource
import shutil
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

_BWRAP = shutil.which("bwrap")


def is_available() -> bool:
    """Check if any sandboxing is available (always True — resource limits work everywhere)."""
    return True


def _bwrap_works() -> bool:
    """Test if bwrap actually works in this environment."""
    if not _BWRAP:
        return False
    try:
        r = subprocess.run(
            [_BWRAP, "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


# Cache bwrap availability check
_bwrap_available: Optional[bool] = None


def _check_bwrap() -> bool:
    global _bwrap_available
    if _bwrap_available is None:
        _bwrap_available = _bwrap_works()
        if _bwrap_available:
            logger.info("Sandbox: bubblewrap available for full isolation")
        else:
            logger.info("Sandbox: using resource limits (bwrap unavailable in this environment)")
    return _bwrap_available


def run_sandboxed(
    script: str,
    *,
    python_path: Optional[str] = None,
    timeout: int = 30,
    allow_network: bool = False,
    writable_dirs: Optional[list] = None,
    env: Optional[dict] = None,
    max_memory_mb: int = 512,
    max_file_size_mb: int = 50,
) -> dict:
    """Execute a Python script with sandboxing.

    Uses bwrap if available, otherwise applies resource limits.

    Args:
        script: Python source code to execute.
        python_path: Path to Python interpreter.
        timeout: Max execution time in seconds.
        allow_network: Whether to allow network access (bwrap only).
        writable_dirs: Additional writable directories (bwrap only).
        env: Environment variables to pass through.
        max_memory_mb: Memory limit in MB.
        max_file_size_mb: Max file write size in MB.

    Returns:
        Dict with 'success', 'stdout', 'stderr', 'returncode', 'sandbox_level'.
    """
    python_path = python_path or _default_python()

    # Write script to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="hermes_sandbox_") as f:
        f.write(script)
        script_path = f.name

    try:
        if _check_bwrap():
            return _run_with_bwrap(script_path, python_path, timeout, allow_network, writable_dirs or [], env)
        else:
            return _run_with_limits(script_path, python_path, timeout, env, max_memory_mb, max_file_size_mb)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _run_with_bwrap(script_path, python_path, timeout, allow_network, writable_dirs, env):
    """Full isolation via bubblewrap."""
    cmd = [_BWRAP, "--ro-bind", "/", "/", "--tmpfs", "/tmp",
           "--ro-bind", script_path, script_path,
           "--proc", "/proc", "--dev", "/dev", "--die-with-parent"]
    for d in writable_dirs:
        if os.path.isdir(d):
            cmd += ["--bind", d, d]
    if not allow_network:
        cmd += ["--unshare-net"]
    cmd += ["--", python_path, script_path]

    run_env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=run_env)
        # Retry without --unshare-net if it failed
        if proc.returncode != 0 and "loopback" in proc.stderr:
            cmd = [x for x in cmd if x != "--unshare-net"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=run_env)
        return {"success": proc.returncode == 0, "stdout": proc.stdout,
                "stderr": proc.stderr, "returncode": proc.returncode, "sandbox_level": "bwrap"}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1, "sandbox_level": "bwrap"}


def _run_with_limits(script_path, python_path, timeout, env, max_memory_mb, max_file_size_mb):
    """Resource-limited execution (no filesystem isolation but prevents resource abuse)."""
    # Wrapper script that sets resource limits before executing the target
    limit_wrapper = f'''
import resource, sys, os
# Memory limit
resource.setrlimit(resource.RLIMIT_AS, ({max_memory_mb * 1024 * 1024}, {max_memory_mb * 1024 * 1024}))
# File size limit
resource.setrlimit(resource.RLIMIT_FSIZE, ({max_file_size_mb * 1024 * 1024}, {max_file_size_mb * 1024 * 1024}))
# CPU time limit
resource.setrlimit(resource.RLIMIT_CPU, ({timeout}, {timeout}))
# No core dumps
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
# Execute the actual script
exec(open("{script_path}").read())
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="hermes_rlimit_") as f:
        f.write(limit_wrapper)
        wrapper_path = f.name

    run_env = dict(os.environ)
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(
            [python_path, wrapper_path],
            capture_output=True, text=True, timeout=timeout + 5, env=run_env,
        )
        return {"success": proc.returncode == 0, "stdout": proc.stdout,
                "stderr": proc.stderr, "returncode": proc.returncode, "sandbox_level": "resource_limits"}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1, "sandbox_level": "resource_limits"}
    finally:
        try:
            os.unlink(wrapper_path)
        except OSError:
            pass


def _default_python() -> str:
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    venv_python = os.path.join(hermes_home, "hermes-agent", "venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return shutil.which("python3") or "python3"
