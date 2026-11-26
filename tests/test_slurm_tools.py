"""Unit tests (no Docker) + live tests (need `make up`). Run live ones with: pytest -m live"""
import pytest

from clustermedic.tools._exec import ToolError, check_allowed
from clustermedic.tools.slurm import parse_kv, parse_sinfo, parse_squeue

# ---------- unit tests: parsing and allowlist ----------

def test_parse_sinfo_healthy_and_drained():
    text = "c1|cpu*|drain|2|1000|week1-test\nc2|cpu*|idle|2|1000|none\n"
    nodes = parse_sinfo(text)
    assert nodes[0] == {"node": "c1", "partition": "cpu", "state": "drain", "healthy": False,
                        "cpus": 2, "memory_mb": 1000, "reason": "week1-test"}
    assert nodes[1]["healthy"] is True and nodes[1]["reason"] is None


def test_parse_kv_handles_values_with_spaces():
    line = "NodeName=c1 State=IDLE+DRAIN Reason=disk full on /tmp [root@2026-11-25T19:00:00] Weight=1"
    kv = parse_kv(line)
    assert kv["NodeName"] == "c1"
    assert kv["State"] == "IDLE+DRAIN"
    assert kv["Reason"] == "disk full on /tmp [root@2026-11-25T19:00:00]"
    assert kv["Weight"] == "1"


def test_parse_squeue():
    jobs = parse_squeue("12|alice|PENDING|cpu||Resources\n13|bob|RUNNING|cpu|c1|None\n")
    assert jobs[0]["nodes"] is None and jobs[0]["reason"] == "Resources"
    assert jobs[1]["nodes"] == "c1" and jobs[1]["reason"] is None


@pytest.mark.parametrize("argv", [
    ["scontrol", "update", "nodename=c1", "state=resume"],
    ["scancel", "12"],
    ["rm", "-rf", "/"],
    [],
])
def test_allowlist_refuses_mutating_commands(argv):
    with pytest.raises(ToolError):
        check_allowed(argv)


def test_allowlist_permits_read_only():
    check_allowed(["sinfo", "-h"])
    check_allowed(["scontrol", "show", "node", "c1"])

# ---------- live tests: need the running stack ----------

@pytest.mark.live
def test_live_sinfo_sees_both_nodes():
    from clustermedic.tools.slurm import sinfo_nodes
    names = {n["node"] for n in sinfo_nodes()}
    assert {"c1", "c2"} <= names


@pytest.mark.live
def test_live_node_info():
    from clustermedic.tools.slurm import node_info
    info = node_info("c1")
    assert info["NodeName"] == "c1" and "State" in info


def test_node_info_rejects_injection():
    from clustermedic.tools.slurm import node_info
    with pytest.raises(ValueError):
        node_info("c1; rm -rf /")
