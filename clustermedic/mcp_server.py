"""ClusterMedic read-only tools as an MCP server (stdio).

Any MCP client (Claude Desktop, an IDE, another agent) can inspect the cluster through these
tools. Nothing here changes state: every tool is a read-only wrapper with the same allowlist,
path guards and timeouts as the agent's own tools. Remediation is NOT exposed over MCP; it
stays inside the agent's human-approval flow.

Run:  python -m clustermedic.mcp_server
"""
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from clustermedic.agent import evidence
from clustermedic.tools import prometheus as prom
from clustermedic.tools import redfish, slurm

server = MCPServer(
    name="clustermedic",
    instructions="Read-only inspection of a simulated Slurm GPU cluster: scheduler state, "
                 "GPU telemetry (DCGM format), BMC sensors (Redfish) and runbook search.",
)
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                     openWorldHint=False)


@server.tool(annotations=RO)
def cluster_anomalies() -> list[str]:
    """Run every health check and return a plain-English list of problems (empty = healthy)."""
    return evidence.anomalies(evidence.gather())


@server.tool(annotations=RO)
def slurm_nodes() -> list[dict]:
    """All Slurm nodes with state, whether slurmd is responding, resources and drain reason."""
    return slurm.sinfo_nodes()


@server.tool(annotations=RO)
def slurm_node_details(node: str) -> dict:
    """Full `scontrol show node` details for one node, e.g. node='c1'."""
    return slurm.node_info(node)


@server.tool(annotations=RO)
def slurm_queue(node: str | None = None, state: str | None = None) -> list[dict]:
    """Jobs in the queue, optionally filtered by node (e.g. 'c2') and/or state (e.g. 'PD')."""
    return slurm.squeue_jobs(node=node, state=state)


@server.tool(annotations=RO)
def gpu_problems(temp_threshold_c: float = 85) -> dict:
    """GPUs that are hot, report a non-zero Xid, or have new double-bit ECC errors."""
    return {"hot": prom.gpu_hot(temp_threshold_c), "xid": prom.gpu_xid(),
            "new_double_bit_ecc_15m": prom.gpu_new_dbe("15m")}


@server.tool(annotations=RO)
def prometheus_query(promql: str) -> list[dict]:
    """Run an instant PromQL query (read-only), e.g. 'DCGM_FI_DEV_GPU_TEMP > 80'."""
    return prom.prom_query(promql)


@server.tool(annotations=RO)
def bmc_thermal() -> dict:
    """Temperatures and fans reported by the BMC (Redfish) for every chassis."""
    return {c: redfish.thermal(c) for c in redfish.chassis_list()}


@server.tool(annotations=RO)
def search_runbooks(query: str, k: int = 4) -> list[dict]:
    """Search the incident runbooks (hybrid keyword + embedding search; keyword-only if the
    embedding model is unavailable). Returns runbook id, section and text."""
    from clustermedic.rag.store import BM25Retriever
    try:
        from clustermedic.rag.__main__ import _retriever
        hits = _retriever("hybrid").search(query, k=min(k, 10))
    except Exception:
        hits = BM25Retriever().search(query, k=min(k, 10))
    return [{"id": h["id"], "runbook": h["runbook"], "section": h["section"], "text": h["text"]}
            for h in hits]


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
