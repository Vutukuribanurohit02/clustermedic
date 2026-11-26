"""Prometheus read-only tools: instant PromQL queries plus ready-made GPU checks."""
import os

from ._exec import ToolError
from ._http import get_json

PROM_URL = os.getenv("CLUSTERMEDIC_PROM_URL", "http://localhost:9090")
MAX_QUERY_LEN = 500


def parse_vector(doc: dict) -> list[dict]:
    """Turn a Prometheus instant-vector response into [{labels..., 'value': float}]."""
    if doc.get("status") != "success":
        raise ToolError(f"Prometheus error: {doc.get('error', 'unknown')}")
    data = doc.get("data", {})
    if data.get("resultType") != "vector":
        raise ToolError(f"expected vector result, got {data.get('resultType')}")
    return [{**r["metric"], "value": float(r["value"][1])} for r in data.get("result", [])]


def prom_query(expr: str) -> list[dict]:
    """Run an instant PromQL query (read-only HTTP GET)."""
    if not expr or len(expr) > MAX_QUERY_LEN:
        raise ToolError("query empty or too long")
    return parse_vector(get_json(f"{PROM_URL}/api/v1/query", params={"query": expr}))


def targets_down() -> list[dict]:
    """Scrape targets Prometheus currently cannot reach."""
    return prom_query("up == 0")


def gpu_hot(threshold_c: float = 85) -> list[dict]:
    """GPUs above a temperature threshold."""
    return prom_query(f"DCGM_FI_DEV_GPU_TEMP > {float(threshold_c)}")


def gpu_new_dbe(window: str = "15m") -> list[dict]:
    """GPUs with new uncorrectable (double-bit) ECC errors in the window."""
    if window not in {"2m", "5m", "15m", "1h", "24h"}:
        raise ToolError(f"unsupported window: {window}")
    return prom_query(f"increase(DCGM_FI_DEV_ECC_DBE_VOL_TOTAL[{window}]) > 0")


def gpu_xid() -> list[dict]:
    """GPUs whose last Xid error code is non-zero."""
    return prom_query("DCGM_FI_DEV_XID_ERRORS != 0")
