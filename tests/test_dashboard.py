"""The provisioned dashboard must be valid JSON and only query metrics we actually export."""
import json
import re
from pathlib import Path

DASH = json.loads(Path("infra/grafana/dashboards/clustermedic.json").read_text())
KNOWN = {"clustermedic_anomalies", "clustermedic_node_healthy", "clustermedic_node_responding",
         "clustermedic_pending_jobs", "clustermedic_pending_approvals", "clustermedic_tool_errors",
         "clustermedic_bmc_temperature_celsius", "clustermedic_bmc_fan_rpm", "clustermedic_incidents",
         "clustermedic_time_to_diagnosis_seconds", "clustermedic_needs_review",
         "DCGM_FI_DEV_GPU_TEMP", "DCGM_FI_DEV_XID_ERRORS", "DCGM_FI_DEV_ECC_DBE_VOL_TOTAL",
         "DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL", "ALERTS"}


def test_dashboard_structure():
    assert DASH["uid"] == "clustermedic"
    ids = [p["id"] for p in DASH["panels"]]
    assert len(ids) == len(set(ids))
    for p in DASH["panels"]:
        if p["type"] != "row":
            assert p["datasource"]["uid"] == "prometheus" and p["targets"]


def test_dashboard_only_uses_exported_metrics():
    for p in DASH["panels"]:
        for t in p.get("targets", []):
            names = set(re.findall(r"\b(clustermedic_[a-z_]+|DCGM_FI_[A-Z_]+|ALERTS)\b", t["expr"]))
            assert names and names <= KNOWN, (p["title"], names - KNOWN)
