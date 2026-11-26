"""Step 1 of the agent: collect evidence with read-only tools and flag anomalies.

Deterministic on purpose. On a small cluster it is cheap to run every check, and a 7B local
model is unreliable at choosing tools. The LLM's job (next step) is reasoning over this evidence.
A failed tool call is recorded as evidence too: "Redfish unreachable" is itself a symptom.
"""
from clustermedic.tools import prometheus as prom
from clustermedic.tools import redfish, slurm

GPU_TEMP_WARN_C = 85
CHECKS = {
    "nodes": slurm.sinfo_nodes,
    "pending_jobs": lambda: slurm.squeue_jobs(state="PD"),
    "gpu_hot": lambda: prom.gpu_hot(GPU_TEMP_WARN_C),
    "gpu_xid": prom.gpu_xid,
    "gpu_new_dbe": lambda: prom.gpu_new_dbe("5m"),
    "gpu_new_sbe": lambda: prom.prom_query("increase(DCGM_FI_DEV_ECC_SBE_VOL_TOTAL[5m]) > 0"),
    "nvlink_errors": lambda: prom.prom_query(
        "increase(DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL[5m]) > 0"),
    "targets_down": prom.targets_down,
    "bmc_thermal": lambda: {c: redfish.thermal(c) for c in redfish.chassis_list()},
}


def gather() -> dict:
    evidence, errors = {}, {}
    for name, fn in CHECKS.items():
        try:
            evidence[name] = fn()
        except Exception as e:  # tool failure is evidence
            errors[name] = str(e)
    evidence["tool_errors"] = errors
    return evidence


def _gpu(r: dict) -> str:
    return f"GPU {r.get('Hostname')}:{r.get('gpu')}"


def anomalies(ev: dict) -> list[str]:
    """Human-readable list of everything that looks wrong. Empty list = nothing found."""
    out = []
    for n in ev.get("nodes", []):
        if not n["responding"]:
            out.append(f"node {n['node']} not responding (slurmd unreachable; state {n['state']}*)")
        elif not n["healthy"]:
            reason = f", reason '{n['reason']}'" if n["reason"] else ""
            out.append(f"node {n['node']} state {n['state']}{reason}")
    for j in ev.get("pending_jobs", []):
        out.append(f"job {j['job_id']} ({j['user']}) pending, reason {j['reason']}")
    for r in ev.get("gpu_hot", []):
        out.append(f"{_gpu(r)} temperature {r['value']:.0f} C (warn {GPU_TEMP_WARN_C} C)")
    for r in ev.get("gpu_xid", []):
        out.append(f"{_gpu(r)} last Xid error {int(r['value'])}")
    for r in ev.get("gpu_new_dbe", []):
        out.append(f"{_gpu(r)} new double-bit (uncorrectable) ECC errors in 5m: {r['value']:.0f}")
    for r in ev.get("gpu_new_sbe", []):
        out.append(f"{_gpu(r)} new single-bit ECC errors in 5m: {r['value']:.0f}")
    for r in ev.get("nvlink_errors", []):
        out.append(f"{_gpu(r)} NVLink CRC errors in 5m: {r['value']:.0f}")
    for r in ev.get("targets_down", []):
        out.append(f"monitoring target down: {r.get('job')} ({r.get('instance')})")
    for chassis, t in ev.get("bmc_thermal", {}).items():
        for f in t["fans"]:
            if f["reporting"] and (f["health"] not in (None, "OK") or not f["reading"]):
                out.append(f"BMC {chassis}: fan '{f['name']}' reading {f['reading']} {f['units']}, "
                           f"health {f['health']}")
        for s in t["temperatures"]:
            crit = s.get("upper_critical")
            if s["reporting"] and (s["health"] not in (None, "OK") or
                                   (crit is not None and s["celsius"] >= crit)):
                out.append(f"BMC {chassis}: '{s['name']}' {s['celsius']} C "
                           f"(critical {crit} C), health {s['health']}")
    for name, err in ev.get("tool_errors", {}).items():
        out.append(f"tool '{name}' failed: {err}")
    return out
