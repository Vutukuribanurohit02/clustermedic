"""Anomaly detection on canned evidence (no Docker)."""
from clustermedic.agent.evidence import anomalies

HEALTHY_NODE = {"node": "c1", "partition": "cpu", "state": "idle", "responding": True,
                "healthy": True, "cpus": 20, "memory_mb": 9942, "reason": None}
THERMAL_OK = {"temperatures": [
    {"name": "CPU1 Temp", "celsius": 41, "upper_critical": 45, "health": "OK",
     "state": "Enabled", "absent": False, "reporting": True},
    {"name": "CPU2 Temp", "celsius": None, "upper_critical": 45, "health": None,
     "state": "Disabled", "absent": False, "reporting": False}],
    "fans": [{"name": "Fan", "reading": 2100, "units": "RPM", "health": "OK",
              "state": "Enabled", "absent": False, "reporting": True}]}


def test_healthy_cluster_has_no_anomalies():
    ev = {"nodes": [HEALTHY_NODE], "bmc_thermal": {"1U": THERMAL_OK}, "tool_errors": {}}
    assert anomalies(ev) == []   # the Disabled CPU2 sensor must NOT be flagged


def test_flags_each_fault_type():
    dead = {**HEALTHY_NODE, "node": "c2", "responding": False, "healthy": False}
    drained = {**HEALTHY_NODE, "state": "drain", "healthy": False, "reason": "Kill task failed"}
    fan_dead = {**THERMAL_OK, "fans": [{**THERMAL_OK["fans"][0], "reading": 0,
                                        "health": "Critical"}]}
    ev = {
        "nodes": [drained, dead],
        "pending_jobs": [{"job_id": "3", "user": "root", "reason": "Resources"}],
        "gpu_hot": [{"Hostname": "c1", "gpu": "0", "value": 93.0}],
        "gpu_xid": [{"Hostname": "c2", "gpu": "1", "value": 79.0}],
        "nvlink_errors": [{"Hostname": "c1", "gpu": "1", "value": 400.0}],
        "bmc_thermal": {"1U": fan_dead},
        "tool_errors": {"targets_down": "GET failed"},
    }
    text = "\n".join(anomalies(ev))
    for needle in ["Kill task failed", "c2 not responding", "pending, reason Resources",
                   "GPU c1:0 temperature 93", "Xid error 79", "NVLink", "reading 0 RPM",
                   "tool 'targets_down' failed"]:
        assert needle in text, needle
