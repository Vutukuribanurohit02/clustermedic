"""Slurm read-only tools: node list, node details, job queue."""
import re

from ._exec import run_slurm

HEALTHY_STATES = {"idle", "mix", "alloc"}
_KV = re.compile(r"(\S+?)=(.*?)(?=\s+\S+?=|$)")


def parse_sinfo(text: str) -> list[dict]:
    """Parse `sinfo -h -N -o '%N|%P|%t|%c|%m|%E'` output."""
    nodes = []
    for line in text.strip().splitlines():
        name, partition, state, cpus, mem, reason = line.split("|", 5)
        nodes.append({
            "node": name,
            "partition": partition.rstrip("*"),
            "state": state,
            "healthy": state in HEALTHY_STATES,
            "cpus": int(cpus),
            "memory_mb": int(mem),
            "reason": None if reason in ("none", "") else reason,
        })
    return nodes


def parse_kv(line: str) -> dict:
    """Parse one-line `Key=Value Key2=Value with spaces` output from `scontrol -o`."""
    return {k: v.strip() for k, v in _KV.findall(line.strip())}


def parse_squeue(text: str) -> list[dict]:
    """Parse `squeue -h -o '%i|%u|%T|%P|%N|%r'` output."""
    jobs = []
    for line in text.strip().splitlines():
        job_id, user, state, partition, nodes, reason = line.split("|", 5)
        jobs.append({"job_id": job_id, "user": user, "state": state,
                     "partition": partition, "nodes": nodes or None,
                     "reason": None if reason == "None" else reason})
    return jobs


def sinfo_nodes() -> list[dict]:
    """All nodes with state, partition, resources and drain/down reason."""
    return parse_sinfo(run_slurm(["sinfo", "-h", "-N", "-o", "%N|%P|%t|%c|%m|%E"]))


def node_info(node: str) -> dict:
    """Full `scontrol show node` details for one node."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", node):
        raise ValueError(f"invalid node name: {node!r}")
    return parse_kv(run_slurm(["scontrol", "show", "node", node, "-o"]))


def squeue_jobs(node: str | None = None, state: str | None = None) -> list[dict]:
    """Jobs in the queue, optionally filtered by node and/or state (e.g. 'PD')."""
    argv = ["squeue", "-h", "-o", "%i|%u|%T|%P|%N|%r"]
    if node:
        argv += ["-w", node]
    if state:
        argv += ["-t", state]
    out = run_slurm(argv)
    return parse_squeue(out) if out.strip() else []
