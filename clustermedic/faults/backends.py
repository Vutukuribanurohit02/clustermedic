"""Low-level helpers the faults use: docker, Slurm admin commands, GPU state file, Redfish mockup."""
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GPU_STATE = REPO / "infra/gpu-exporter/state/faults.json"
REDFISH_MOCKUP = REPO / "infra/redfish/mockups/public-rackmount1"
SLURM_CTL = "slurmctld"


class InjectError(RuntimeError):
    pass


def sh(cmd: list[str], check: bool = True) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if check and out.returncode != 0:
        raise InjectError(f"{' '.join(cmd)} failed: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout.strip()


def wait_for(check, timeout_s: int, what: str, interval_s: int = 5) -> None:
    """Poll check() until it returns True, or fail after timeout_s."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if check():
                return
        except InjectError:
            pass
        time.sleep(interval_s)
    raise InjectError(f"timed out after {timeout_s}s waiting for {what}")


def slurm_admin(*args: str) -> str:
    """Admin Slurm command in the controller. Only the injector uses this, never the agent."""
    return sh(["docker", "exec", SLURM_CTL, *args])


def container_for_node(node: str) -> str:
    """Find the worker container behind a Slurm node (e.g. c1 -> slurm-cpu-worker-1).

    Slurm's NodeAddr/NodeHostName may be an IP, a container name or a container hostname,
    so match on any of those.
    """
    info = slurm_admin("scontrol", "show", "node", node, "-o")
    wanted = {node}
    for field in info.split():
        if field.startswith(("NodeAddr=", "NodeHostName=")):
            wanted.add(field.split("=", 1)[1])
    for name in sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines():
        ids = sh(["docker", "inspect", "-f",
                  "{{.Config.Hostname}} {{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                  name], check=False).split()
        if wanted & ({name} | set(ids)):
            return name
    raise InjectError(f"no container found for node {node!r} (looked for {sorted(wanted)})")


# ---------- GPU exporter state file ----------

def gpu_state_read() -> dict:
    try:
        return json.loads(GPU_STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def gpu_state_set(key: str, fault: dict) -> None:
    state = gpu_state_read()
    state[key] = fault
    GPU_STATE.parent.mkdir(parents=True, exist_ok=True)
    GPU_STATE.write_text(json.dumps(state, indent=2))


def gpu_state_clear(key: str) -> None:
    state = gpu_state_read()
    state.pop(key, None)
    GPU_STATE.write_text(json.dumps(state, indent=2))


# ---------- Redfish mockup editing ----------

def restart_redfish(timeout_s: int = 30) -> None:
    """Restart the mockup server and wait until it answers again."""
    sh(["docker", "restart", "redfish"])
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:8000/redfish/v1", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise InjectError(f"redfish did not come back within {timeout_s}s")

def _thermal_file(mockup: Path = None) -> Path:
    mockup = mockup or REDFISH_MOCKUP
    hits = list(mockup.rglob("Chassis/1U/Thermal/index.json"))
    if not hits:
        raise InjectError(f"Thermal index.json not found under {mockup}; run scripts/setup_redfish_mockup.sh")
    return hits[0]


def redfish_edit_thermal(edit, mockup: Path = None, restart: bool = True) -> None:
    """Apply edit(doc) to the Thermal resource; keep a pristine .orig copy for clearing."""
    f = _thermal_file(mockup)
    orig = f.with_suffix(".json.orig")
    if not orig.exists():
        shutil.copy(f, orig)
    doc = json.loads(f.read_text())
    edit(doc)
    f.write_text(json.dumps(doc, indent=4))
    if restart:
        restart_redfish()


def redfish_restore_thermal(mockup: Path = None, restart: bool = True) -> None:
    f = _thermal_file(mockup)
    orig = f.with_suffix(".json.orig")
    if orig.exists():
        shutil.copy(orig, f)
        orig.unlink()
    if restart:
        restart_redfish()
