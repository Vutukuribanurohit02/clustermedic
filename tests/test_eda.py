"""EDA triage tests. Yosys fixtures are real tool output; STA/DRC fixtures are hand-written."""
import json
import shutil
from pathlib import Path

import pytest

from clustermedic.eda import diagnose as dx
from clustermedic.eda import evidence, parsers

FIX = Path("tests/fixtures/eda")


def test_sta_setup_path_details():
    p = parsers.parse_sta_paths((FIX / "sta_setup.rpt").read_text())[0]
    assert p["startpoint"] == "_692_" and p["endpoint"] == "_704_" and p["path_group"] == "core_clock"
    assert p["violated"] and p["slack"] == -0.43 and p["path_type"] == "max"
    assert p["logic_levels"] == 4            # nand2, a21o, xnor2, a31o (flops and clock buffers excluded)
    assert p["max_fanout"] == 18 and "sky130_fd_sc_hd__nand2_1" in p["weakest_cells"]
    assert parsers.parse_slack_summary((FIX / "sta_setup.rpt").read_text()) == {"wns": -0.43, "tns": -6.21}


def test_primetime_style_report():
    p = parsers.parse_sta_paths((FIX / "sta_primetime.rpt").read_text())[0]
    assert p["violated"] and p["slack"] == -0.54 and p["endpoint"] == "u_uart/baud_cnt_reg_7_"
    assert p["arrival"] == 10.42 and p["required"] == 9.88


def test_drc_counts():
    d = parsers.parse_drc((FIX / "drc_route.rpt").read_text())
    assert d == {"total": 3, "by_type": {"Short": 2, "Metal Spacing": 1}, "by_layer": {"met1": 2, "met2": 1}}
    assert parsers.parse_drc("[INFO DRT-0199]   Number of violations = 12.")["total"] == 12


@pytest.mark.parametrize("name,cause", [("clean", "no_issue"), ("latch", "latch_inferred"),
                                        ("undriven", "undriven_net"), ("multidriver", "multiple_drivers")])
def test_real_yosys_logs_classified(tmp_path, name, cause):
    shutil.copy(FIX / f"yosys_{name}.log", tmp_path / "yosys.log")
    found = evidence.anomalies(evidence.gather(tmp_path))
    assert dx.diagnose_rules(found)["root_cause"] == cause
    if cause != "no_issue":
        assert dx.is_grounded(cause, found)


def test_run_dir_prefers_final_stage_and_combines_sources(tmp_path):
    (tmp_path / "reports").mkdir()
    shutil.copy(FIX / "sta_met.rpt", tmp_path / "reports/4_cts_final.rpt")
    shutil.copy(FIX / "sta_setup.rpt", tmp_path / "reports/6_finish.rpt")
    shutil.copy(FIX / "drc_route.rpt", tmp_path / "reports/5_route_drc.rpt")
    ev = evidence.gather(tmp_path)
    assert ev["sta_source"] == "6_finish.rpt" and ev["drc"]["total"] == 3
    found = evidence.anomalies(ev)
    assert any(a.startswith("setup timing violated: worst slack -0.430") for a in found)
    assert any(a.startswith("DRC: 3 violations") for a in found)
    assert dx.diagnose_rules(found)["root_cause"] == "setup_violation"


def test_flow_error_and_placement_priority():
    found = ["flow error [GPL-0302] in 3_3_place_gp.log: Use a higher -density or re-floorplan "
             "with a larger core area.", "DRC: 4 violations after routing (4 Short)"]
    assert dx.diagnose_rules(found)["root_cause"] == "placement_density"
    assert dx.diagnose_rules(["flow error [DRT-0001] in 5_2_route.log: x"])["root_cause"] == "flow_error"


def test_llm_ungrounded_answer_is_flagged_and_gets_no_fixes(monkeypatch):
    monkeypatch.setattr(dx, "chat_json", lambda *a, **k: {
        "root_cause": "hold_violation", "location": "x", "confidence": 0.9, "evidence": [],
        "explanation": "e", "recommended_fixes": ["do something"]})
    ev = {"paths": [], "yosys": {"latches": ["top.q"], "undriven": [], "multiple_drivers": []}}
    out = dx.diagnose_llm(ev, ["synthesis: latch inferred for signal top.q"], [])
    assert not out["grounded"] and out["needs_review"] and out["evidence_based_fixes"] == []


def test_evidence_based_fixes_name_the_path():
    paths = parsers.parse_sta_paths((FIX / "sta_setup.rpt").read_text())
    recs = dx.recommendations("setup_violation", {"paths": paths})
    assert "_692_ -> _704_" in recs[0] and any("fanout 18" in r for r in recs)


def test_labels_cover_only_known_causes():
    labels = json.loads(Path("eda/labels.json").read_text())
    assert set(labels.values()) <= set(dx.CAUSES)


def test_latch_warning_optimized_away_is_not_a_problem(tmp_path):
    # Seen on real ORFS gcd: Yosys warns "Latch inferred" but synth_stat.txt has no latch cells.
    (tmp_path / "logs").mkdir(); (tmp_path / "reports").mkdir()
    (tmp_path / "logs/1_2_yosys.log").write_text(
        "Warning: Latch inferred for signal `\\Gcd.\\do_sub' from process `x': y\n")
    (tmp_path / "reports/synth_stat.txt").write_text(
        "   Number of cells:   312\n     40   sky130_fd_sc_hd__dfxtp_1\n"
        "      3   sky130_fd_sc_hd__dlygate4sd3_1\n      1   sky130_fd_sc_hd__dlclkp_1\n")
    shutil.copy(FIX / "sta_setup.rpt", tmp_path / "reports/6_finish.rpt")
    ev = evidence.gather(tmp_path)
    assert ev["yosys"]["latch_cells"] == 0
    found = evidence.anomalies(ev)
    assert any(a.startswith("note: Yosys warned") for a in found)
    assert dx.diagnose_rules(found)["root_cause"] == "setup_violation"   # real problem not hidden


def test_note_only_means_no_issue(monkeypatch):
    monkeypatch.setattr(dx, "chat_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    out = dx.diagnose_llm({}, ["note: Yosys warned about possible latches (x) but 0 latch cells remain"], [])
    assert out["root_cause"] == "no_issue" and out["grounded"]


def test_latch_cells_counted():
    assert parsers.parse_latch_cells("Number of cells: 9\n   2   sky130_fd_sc_hd__dlxtp_1\n"
                                     "   sky130_fd_sc_hd__dlrtp_1     3\n") == 5
    assert parsers.parse_latch_cells((FIX / "yosys_latch.log").read_text()) == 8      # real: 8 $_DLATCH_P_
    assert parsers.parse_latch_cells((FIX / "yosys_clean.log").read_text()) == 0
    assert parsers.parse_latch_cells("no statistics here") is None


def test_empty_run_is_refused(tmp_path):
    import pytest
    from clustermedic.eda.__main__ import triage
    (tmp_path / "logs").mkdir()
    with pytest.raises(SystemExit):
        triage(tmp_path, retriever=object())
