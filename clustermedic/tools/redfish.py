"""Redfish (BMC) read-only tools: chassis list and thermal readings (temperatures, fans)."""
import os
import re

from ._exec import ToolError
from ._http import get_json

REDFISH_URL = os.getenv("CLUSTERMEDIC_REDFISH_URL", "http://localhost:8000")
_SAFE_ID = re.compile(r"[A-Za-z0-9_.-]+")


def redfish_get(path: str) -> dict:
    """GET a Redfish resource. Only paths under /redfish/v1/ are allowed."""
    if not path.startswith("/redfish/v1") or ".." in path:
        raise ToolError(f"refusing non-Redfish path: {path!r}")
    return get_json(REDFISH_URL + path)


def _status(item: dict) -> tuple[str | None, str | None]:
    s = item.get("Status") or {}
    return s.get("Health"), s.get("State")


def parse_thermal(doc: dict) -> dict:
    """Normalise a Redfish Thermal resource into temperatures and fans.

    `reporting` is True only for an enabled sensor with a value. A Disabled or Absent
    sensor with no reading is not a failure (e.g. an empty CPU socket).
    """
    temps, fans = [], []
    for t in doc.get("Temperatures", []):
        health, state = _status(t)
        temps.append({
            "name": t.get("Name"),
            "celsius": t.get("ReadingCelsius"),
            "upper_critical": t.get("UpperThresholdCritical"),
            "health": health,
            "state": state,
            "absent": state == "Absent",
            "reporting": state == "Enabled" and t.get("ReadingCelsius") is not None,
        })
    for f in doc.get("Fans", []):
        health, state = _status(f)
        fans.append({
            "name": f.get("Name") or f.get("FanName"),
            "reading": f.get("Reading"),
            "units": f.get("ReadingUnits"),
            "health": health,
            "state": state,
            "absent": state == "Absent",
            "reporting": state == "Enabled" and f.get("Reading") is not None,
        })
    return {"temperatures": temps, "fans": fans}


def chassis_list() -> list[str]:
    """IDs of all chassis the BMC reports."""
    doc = redfish_get("/redfish/v1/Chassis")
    return [m["@odata.id"].rstrip("/").split("/")[-1] for m in doc.get("Members", [])]


def thermal(chassis_id: str) -> dict:
    """Temperatures and fans for one chassis."""
    if not _SAFE_ID.fullmatch(chassis_id):
        raise ValueError(f"invalid chassis id: {chassis_id!r}")
    return parse_thermal(redfish_get(f"/redfish/v1/Chassis/{chassis_id}/Thermal"))
