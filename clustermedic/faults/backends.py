"""Low-level helpers the faults use: docker, Slurm admin commands, GPU state file, Redfish mockup."""
import json
import shutil
import subprocess
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


def slurm_admin(*args: str) -> str:
    """Admin Slurm command in the controller. Only the injector uses this, never the agent."""
    return sh(["docker", "exec", SLURM_CTL, *args])


def container_for_node(node: str) -> str:
    """Find the worker container whose hostname is `node` (e.g. c1 -> slurm-cpu-worker-1)."""
    for name in sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines():
        if sh(["docker", "inspect", "-f", "{{.Config.Hostname}}", name], check=False) == node:
            return name
    raise InjectError(f"no container with hostname {node!r}")


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
        sh(["docker", "restart", "redfish"])


def redfish_restore_thermal(mockup: Path = None, restart: bool = True) -> None:
    f = _thermal_file(mockup)
    orig = f.with_suffix(".json.orig")
    if orig.exists():
        shutil.copy(orig, f)
        orig.unlink()
    if restart:
        sh(["docker", "restart", "redfish"])
