"""Synthetic GPU telemetry in NVIDIA dcgm-exporter format (no real data-center GPU needed).

Faults are read from STATE_FILE, keyed "node:gpu", e.g.:
  {"c1:0": {"temp_c": 92, "xid": 48, "ecc_dbe_per_tick": 1, "nvlink_crc_per_tick": 50}}
"""
import json
import os
import random
import time
from pathlib import Path

from prometheus_client import CollectorRegistry, Gauge, start_http_server

PORT = int(os.getenv("PORT", "9400"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/state/faults.json"))
NODES = os.getenv("NODES", "c1,c2").split(",")
GPUS_PER_NODE = int(os.getenv("GPUS_PER_NODE", "2"))
TICK_SECONDS = 5
MODEL = "NVIDIA A100-SXM4-80GB"
LABELS = ["gpu", "UUID", "device", "modelName", "Hostname"]

# Own registry so we only expose DCGM-style metrics (no Python process metrics).
REG = CollectorRegistry()

def gauge(name: str, doc: str) -> Gauge:
    return Gauge(name, doc, LABELS, registry=REG)

# Note: dcgm-exporter marks the *_TOTAL error metrics as counters. We use gauges so the
# names match exactly (prometheus_client would append "_total" to a Counter), but we only
# ever increase them, so rate()/increase() queries still behave like the real thing.
TEMP = gauge("DCGM_FI_DEV_GPU_TEMP", "GPU temperature (in C).")
POWER = gauge("DCGM_FI_DEV_POWER_USAGE", "Power draw (in W).")
UTIL = gauge("DCGM_FI_DEV_GPU_UTIL", "GPU utilization (in %).")
FB_USED = gauge("DCGM_FI_DEV_FB_USED", "Framebuffer memory used (in MiB).")
XID = gauge("DCGM_FI_DEV_XID_ERRORS", "Value of the last XID error encountered.")
ECC_SBE = gauge("DCGM_FI_DEV_ECC_SBE_VOL_TOTAL", "Total single-bit volatile ECC errors.")
ECC_DBE = gauge("DCGM_FI_DEV_ECC_DBE_VOL_TOTAL", "Total double-bit volatile ECC errors.")
NVLINK_CRC = gauge("DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL", "Total NVLink CRC flit errors.")

# Error totals only ever go up, like real hardware counters (until "reboot" = container restart).
totals: dict[str, dict[str, int]] = {}


def load_faults() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def tick() -> None:
    faults = load_faults()
    for node in NODES:
        for i in range(GPUS_PER_NODE):
            key = f"{node}:{i}"
            fault = faults.get(key, {})
            labels = dict(gpu=str(i), UUID=f"GPU-sim-{node}-{i}", device=f"nvidia{i}",
                          modelName=MODEL, Hostname=node)

            t = totals.setdefault(key, {"sbe": 0, "dbe": 0, "crc": 0})
            t["sbe"] += int(fault.get("ecc_sbe_per_tick", 0))
            t["dbe"] += int(fault.get("ecc_dbe_per_tick", 0))
            t["crc"] += int(fault.get("nvlink_crc_per_tick", 0))

            TEMP.labels(**labels).set(fault.get("temp_c", round(random.uniform(38, 45), 1)))
            POWER.labels(**labels).set(round(random.uniform(60, 90), 1))
            UTIL.labels(**labels).set(random.randint(0, 30))
            FB_USED.labels(**labels).set(random.randint(1000, 4000))
            XID.labels(**labels).set(int(fault.get("xid", 0)))
            ECC_SBE.labels(**labels).set(t["sbe"])
            ECC_DBE.labels(**labels).set(t["dbe"])
            NVLINK_CRC.labels(**labels).set(t["crc"])


if __name__ == "__main__":
    start_http_server(PORT, registry=REG)
    print(f"fake dcgm-exporter on :{PORT}, nodes={NODES}, gpus/node={GPUS_PER_NODE}", flush=True)
    while True:
        tick()
        time.sleep(TICK_SECONDS)
