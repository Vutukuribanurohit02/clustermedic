"""Safe command runner: no shell, allowlisted read-only commands, timeouts.

All Slurm commands run inside the controller container via `docker exec`.
"""
import os
import subprocess

SLURM_CONTAINER = os.getenv("CLUSTERMEDIC_SLURM_CONTAINER", "slurmctld")
TIMEOUT_S = 15

# Read-only commands. scontrol is allowed only with "show".
READ_ONLY = {"sinfo", "squeue", "sacct", "sprio", "scontrol"}


class ToolError(RuntimeError):
    """Raised when a command is refused or fails."""


def check_allowed(argv: list[str]) -> None:
    if not argv or argv[0] not in READ_ONLY:
        raise ToolError(f"command not on read-only allowlist: {argv[:1]}")
    if argv[0] == "scontrol" and (len(argv) < 2 or argv[1] != "show"):
        raise ToolError("only 'scontrol show ...' is allowed (read-only)")


def run_slurm(argv: list[str]) -> str:
    """Run an allowlisted Slurm command in the controller container; return stdout."""
    check_allowed(argv)
    cmd = ["docker", "exec", SLURM_CONTAINER, *argv]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise ToolError(f"timed out after {TIMEOUT_S}s: {' '.join(argv)}") from e
    if out.returncode != 0:
        raise ToolError(f"{' '.join(argv)} failed: {out.stderr.strip()}")
    return out.stdout
