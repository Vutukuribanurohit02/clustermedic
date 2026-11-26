"""The fault catalogue. Each fault: what it breaks, its true root cause, and how to undo it."""
from dataclasses import dataclass
from typing import Callable

from . import backends as b


@dataclass(frozen=True)
class Fault:
    name: str
    target: str            # "node", "gpu" or "bmc"
    root_cause: str        # ground-truth label the agent's diagnosis is scored against
    runbook: str           # runbook that should be retrieved
    description: str
    inject: Callable[[dict], dict]   # ctx -> undo info
    clear: Callable[[dict], None]    # undo info -> None


# ----- Slurm faults -----

def _drain(ctx):
    b.slurm_admin("scontrol", "update", f"nodename={ctx['node']}", "state=drain", "reason=Kill task failed")
    return {"node": ctx["node"]}

def _resume(u):
    b.slurm_admin("scontrol", "update", f"nodename={u['node']}", "state=resume")

def _slurmd_down(ctx):
    c = b.container_for_node(ctx["node"])
    b.sh(["docker", "stop", c])
    # Slurm only flags the node ("idle*") after it misses heartbeats; measured ~1.5 min here.
    # Wait so the symptom exists before anyone starts diagnosing.
    b.wait_for(lambda: b.slurm_admin("sinfo", "-h", "-n", ctx["node"], "-o", "%t").endswith("*"),
               timeout_s=360, what=f"{ctx['node']} to show as not responding")
    return {"node": ctx["node"], "container": c}

def _slurmd_up(u):
    b.sh(["docker", "start", u["container"]])
    # The node often re-registers as idle by itself; resume only matters if it is still down.
    b.sh(["docker", "exec", b.SLURM_CTL, "scontrol", "update", f"nodename={u['node']}",
          "state=resume"], check=False)

def _saturate(ctx):
    blocker = b.slurm_admin("sbatch", "--parsable", "-N2", "--exclusive", "-J", "sim_long",
                            "--wrap", "sleep 3600")
    victim = b.slurm_admin("sbatch", "--parsable", "-N1", "-J", "analysis", "--wrap", "hostname")
    return {"jobs": [blocker, victim]}

def _cancel(u):
    for j in u["jobs"]:
        b.sh(["docker", "exec", b.SLURM_CTL, "scancel", j], check=False)

# ----- GPU faults (via the exporter state file) -----

def _gpu(fault: dict):
    def inject(ctx):
        key = f"{ctx['node']}:{ctx['gpu']}"
        b.gpu_state_set(key, fault)
        return {"key": key}
    return inject

def _gpu_clear(u):
    b.gpu_state_clear(u["key"])

# ----- BMC faults (via the Redfish mockup files) -----

def _fan_fail(ctx):
    def edit(doc):
        fan = doc["Fans"][0]
        fan["Reading"] = 0
        fan.setdefault("Status", {})["Health"] = "Critical"
    b.redfish_edit_thermal(edit)
    return {}

def _cpu_hot(ctx):
    def edit(doc):
        t = next(x for x in doc["Temperatures"] if x.get("Name") == "CPU1 Temp")
        t["ReadingCelsius"] = (t.get("UpperThresholdCritical") or 90) + 3
        t.setdefault("Status", {})["Health"] = "Critical"
    b.redfish_edit_thermal(edit)
    return {}

def _redfish_clear(u):
    b.redfish_restore_thermal()


FAULTS: dict[str, Fault] = {f.name: f for f in [
    Fault("node_drain", "node", "node_drained", "RB-001",
          "Drain a node with a realistic reason", _drain, _resume),
    Fault("slurmd_down", "node", "slurmd_down", "RB-003",
          "Stop a worker container so slurmd stops responding", _slurmd_down, _slurmd_up),
    Fault("jobs_pending", "node", "jobs_pending", "RB-010",
          "A long exclusive job holds both nodes; a new job waits on Resources", _saturate, _cancel),
    Fault("gpu_overheat", "gpu", "overheat", "RB-006",
          "GPU temperature 93 C", _gpu({"temp_c": 93}), _gpu_clear),
    Fault("gpu_ecc_dbe", "gpu", "gpu_ecc_xid", "RB-007",
          "Double-bit ECC errors with Xid 48", _gpu({"xid": 48, "ecc_dbe_per_tick": 1}), _gpu_clear),
    Fault("gpu_off_bus", "gpu", "gpu_ecc_xid", "RB-007",
          "GPU fell off the bus (Xid 79)", _gpu({"xid": 79}), _gpu_clear),
    Fault("gpu_sbe_storm", "gpu", "gpu_ecc_xid", "RB-007",
          "High single-bit ECC rate (Xid 92)", _gpu({"xid": 92, "ecc_sbe_per_tick": 25}), _gpu_clear),
    Fault("nvlink_errors", "gpu", "nvlink_errors", "RB-008",
          "NVLink CRC errors rising", _gpu({"nvlink_crc_per_tick": 50}), _gpu_clear),
    Fault("fan_failure", "bmc", "fan_failure", "RB-005",
          "BMC reports the main system fan at 0 RPM, Critical", _fan_fail, _redfish_clear),
    Fault("cpu_overheat", "bmc", "overheat", "RB-006",
          "BMC reports CPU1 above its critical threshold", _cpu_hot, _redfish_clear),
]}
