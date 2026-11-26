"""Unit tests for the fault injector (no Docker needed)."""
import json

import pytest

from clustermedic.faults import backends as b
from clustermedic.faults.registry import FAULTS


def test_catalogue_has_ten_labelled_faults():
    assert len(FAULTS) >= 10
    for f in FAULTS.values():
        assert f.root_cause and f.runbook.startswith("RB-") and f.target in {"node", "gpu", "bmc"}


def test_gpu_fault_writes_and_clears_state(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "GPU_STATE", tmp_path / "faults.json")
    undo = FAULTS["gpu_ecc_dbe"].inject({"node": "c2", "gpu": 1})
    assert json.loads((tmp_path / "faults.json").read_text())["c2:1"]["xid"] == 48
    FAULTS["gpu_ecc_dbe"].clear(undo)
    assert json.loads((tmp_path / "faults.json").read_text()) == {}


def test_redfish_edit_and_restore(tmp_path):
    thermal = tmp_path / "redfish/v1/Chassis/1U/Thermal/index.json"
    thermal.parent.mkdir(parents=True)
    original = {"Temperatures": [{"Name": "CPU1 Temp", "ReadingCelsius": 41,
                                  "UpperThresholdCritical": 45, "Status": {"Health": "OK"}}],
                "Fans": [{"Name": "Fan", "Reading": 2100, "Status": {"Health": "OK"}}]}
    thermal.write_text(json.dumps(original))

    def edit(doc):
        doc["Fans"][0]["Reading"] = 0
    b.redfish_edit_thermal(edit, mockup=tmp_path, restart=False)
    assert json.loads(thermal.read_text())["Fans"][0]["Reading"] == 0
    b.redfish_restore_thermal(mockup=tmp_path, restart=False)
    assert json.loads(thermal.read_text()) == original
