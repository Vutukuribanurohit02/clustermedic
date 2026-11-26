"""Remediation actions the agent may PROPOSE. A human approves every one that changes state.

The LLM never writes commands. It picks a root cause; this table maps the cause to one
allowlisted action with a fixed implementation. Every proposal/decision/result is audited.
"""
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO / "data/audit.jsonl"
NODE_MAP = REPO / "data/node_containers.json"
SLURM_CTL = "slurmctld"


class ActionError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise ActionError(f"{' '.join(cmd)}: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout.strip()


def audit(event: str, **fields) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event,
                            **fields}, default=str) + "\n")


def _node_state(node: str) -> str:
    return _run(["docker", "exec", SLURM_CTL, "sinfo", "-h", "-n", node, "-o", "%t"])


# ---------- lab-only: map Slurm node -> container (needed to restart a stopped node) ----------

def refresh_node_map() -> dict:
    """Record node->container for running nodes; keep old entries for nodes that are down."""
    mapping = json.loads(NODE_MAP.read_text()) if NODE_MAP.exists() else {}
    nodes = _run(["docker", "exec", SLURM_CTL, "sinfo", "-h", "-N", "-o", "%N"]).split()
    running = _run(["docker", "ps", "--format", "{{.Names}}"]).split()
    ips = {}
    for name in running:
        for ip in _run(["docker", "inspect", "-f",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", name]).split():
            ips[ip] = name
    for node in nodes:
        info = _run(["docker", "exec", SLURM_CTL, "scontrol", "show", "node", node, "-o"])
        m = re.search(r"NodeAddr=(\S+)", info)
        if m and m.group(1) in ips:
            mapping[node] = ips[m.group(1)]
    NODE_MAP.parent.mkdir(parents=True, exist_ok=True)
    NODE_MAP.write_text(json.dumps(mapping, indent=2))
    return mapping


# ---------- action implementations ----------

def _resume(target):
    _run(["docker", "exec", SLURM_CTL, "scontrol", "update", f"nodename={target}", "state=resume"])


def _healthy(target):
    s = _node_state(target)
    return s in {"idle", "mix", "alloc"}


def _drain(target, reason="ClusterMedic: hardware fault, awaiting repair"):
    node = target.split(":")[0]
    _run(["docker", "exec", SLURM_CTL, "scontrol", "update", f"nodename={node}",
          "state=drain", f"reason={reason}"])


def _drained(target):
    return _node_state(target.split(":")[0]).startswith(("drain", "drng"))


def _restart_node(target):
    mapping = json.loads(NODE_MAP.read_text()) if NODE_MAP.exists() else {}
    if target not in mapping:
        raise ActionError(f"no known container for {target}; run refresh_node_map while healthy")
    _run(["docker", "start", mapping[target]])
    subprocess.run(["docker", "exec", SLURM_CTL, "scontrol", "update", f"nodename={target}",
                    "state=resume"], capture_output=True, timeout=30)  # may already be idle


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    changes_state: bool                    # True -> human approval required
    apply: Callable[[str], None] | None
    verify: Callable[[str], bool] | None
    target_kind: str                       # "node", "gpu" or "none"


ACTIONS = {a.name: a for a in [
    Action("resume_node", "Return a drained node to service (scontrol ... state=resume)",
           True, _resume, _healthy, "node"),
    Action("restart_node", "Restart the node's slurmd (lab: start its container) and resume it",
           True, _restart_node, _healthy, "node"),
    Action("drain_for_repair", "Drain the node so no new jobs use the faulty hardware; "
           "open a hardware ticket", True, _drain, _drained, "gpu"),
    Action("escalate_hardware", "BMC hardware fault: open a hardware ticket for the on-site team "
           "(no automated change)", False, None, None, "none"),
    Action("report_only", "No safe automated fix; report findings to the user", False,
           None, None, "none"),
]}

CAUSE_TO_ACTION = {
    "node_drained": "resume_node",
    "slurmd_down": "restart_node",
    "gpu_ecc_xid": "drain_for_repair",
    "nvlink_errors": "drain_for_repair",
    "overheat": "drain_for_repair",      # GPU overheat; BMC overheat is re-routed below
    "fan_failure": "escalate_hardware",
    "jobs_pending": "report_only",
    "disk_full": "report_only",
    "munge_auth_failure": "report_only",
    "mtu_mismatch": "report_only",
    "no_fault": "report_only",
}


def normalise_target(cause: str, raw_target: str, anomalies: list[str]) -> str:
    """Turn the model's free-text target into 'c1', 'c1:0' or 'bmc', using the evidence."""
    text = raw_target + "\n" + "\n".join(anomalies)
    if cause in {"fan_failure"} or ("BMC" in raw_target and cause == "overheat"):
        return "bmc"
    if cause in {"gpu_ecc_xid", "nvlink_errors", "overheat"}:
        m = re.search(r"\b(c\d+):(\d+)\b", text)
        if m:
            return f"{m.group(1)}:{m.group(2)}"
        if "BMC" in text:
            return "bmc"
    m = re.search(r"\b(c\d+)\b", text)
    return m.group(1) if m else ""


def propose(diagnosis: dict, anomalies: list[str]) -> dict:
    cause = diagnosis["root_cause"]
    target = normalise_target(cause, diagnosis.get("target", ""), anomalies)
    name = CAUSE_TO_ACTION.get(cause, "report_only")
    if target == "bmc" and name == "drain_for_repair":
        name = "escalate_hardware"
    if diagnosis.get("needs_review") and name != "report_only":
        # Low-trust diagnosis: never auto-propose a state change; hand it to a human.
        name = "report_only"
    a = ACTIONS[name]
    return {"action": name, "target": target, "description": a.description,
            "requires_approval": a.changes_state}


def execute(proposal: dict, verify_timeout_s: int = 60) -> dict:
    a = ACTIONS[proposal["action"]]
    if not a.changes_state:
        return {"applied": False, "verified": None, "note": "no automated change"}
    t0 = time.time()
    a.apply(proposal["target"])
    while time.time() - t0 < verify_timeout_s:
        if a.verify(proposal["target"]):
            return {"applied": True, "verified": True, "seconds": round(time.time() - t0, 1)}
        time.sleep(2)
    return {"applied": True, "verified": False, "seconds": round(time.time() - t0, 1)}
