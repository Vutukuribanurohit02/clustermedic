"""Unit tests use canned JSON; live tests need `make up`."""
import pytest

from clustermedic.tools._exec import ToolError
from clustermedic.tools.prometheus import gpu_new_dbe, parse_vector, prom_query
from clustermedic.tools.redfish import parse_thermal, redfish_get, thermal

THERMAL_DOC = {
    "Temperatures": [
        {"Name": "CPU1 Temp", "ReadingCelsius": 41, "UpperThresholdCritical": 90,
         "Status": {"State": "Enabled", "Health": "OK"}},
        {"Name": "CPU2 Temp", "ReadingCelsius": None, "Status": {"State": "Absent"}},
        {"Name": "CPU3 Temp", "ReadingCelsius": None, "Status": {"State": "Disabled"}},
    ],
    "Fans": [
        {"Name": "BaseBoard System Fan", "Reading": 2100, "ReadingUnits": "RPM",
         "Status": {"State": "Enabled", "Health": "OK"}},
    ],
}


def test_parse_thermal_marks_absent_sensor():
    t = parse_thermal(THERMAL_DOC)
    assert t["temperatures"][0]["celsius"] == 41 and t["temperatures"][0]["absent"] is False
    assert t["temperatures"][1]["celsius"] is None and t["temperatures"][1]["absent"] is True
    assert t["temperatures"][0]["reporting"] is True
    # Disabled with no reading (as in the DMTF mockup's CPU2): not reporting, not a fault
    assert t["temperatures"][2]["reporting"] is False and t["temperatures"][2]["absent"] is False
    assert t["fans"][0] == {"name": "BaseBoard System Fan", "reading": 2100, "units": "RPM",
                            "health": "OK", "state": "Enabled", "absent": False,
                            "reporting": True}


def test_parse_vector():
    doc = {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": {"Hostname": "c1", "gpu": "0"}, "value": [1795653420.0, "92"]}]}}
    assert parse_vector(doc) == [{"Hostname": "c1", "gpu": "0", "value": 92.0}]


def test_parse_vector_error():
    with pytest.raises(ToolError):
        parse_vector({"status": "error", "error": "bad query"})


def test_redfish_path_guard():
    with pytest.raises(ToolError):
        redfish_get("/etc/passwd")
    with pytest.raises(ToolError):
        redfish_get("/redfish/v1/../../secret")


def test_thermal_rejects_bad_id():
    with pytest.raises(ValueError):
        thermal("1U/../../x")


def test_query_and_window_guards():
    with pytest.raises(ToolError):
        prom_query("")
    with pytest.raises(ToolError):
        gpu_new_dbe(window="1d; drop")


@pytest.mark.live
def test_live_redfish_thermal():
    from clustermedic.tools.redfish import chassis_list
    ids = chassis_list()
    assert ids
    t = thermal(ids[0])
    assert any(x["celsius"] is not None for x in t["temperatures"])
    assert t["fans"]


@pytest.mark.live
def test_live_prometheus_targets_up():
    from clustermedic.tools.prometheus import targets_down
    up = prom_query("up")
    assert {r["job"] for r in up} >= {"node", "gpu", "prometheus"}
    assert targets_down() == []
