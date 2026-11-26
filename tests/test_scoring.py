from clustermedic.evaluation.harness import plan
from clustermedic.evaluation.scoring import expected_for, score_row, summarize


def test_expected_targets_and_actions():
    assert expected_for("node_drain", "c2", 0) == {"root_cause": "node_drained", "action": "resume_node", "target": "c2"}
    assert expected_for("gpu_off_bus", "c1", 1)["target"] == "c1:1"
    assert expected_for("cpu_overheat", "c1", 0) == {"root_cause": "overheat", "action": "escalate_hardware", "target": "bmc"}
    assert expected_for("gpu_overheat", "c2", 0)["action"] == "drain_for_repair"
    assert expected_for("jobs_pending", "c1", 0)["target"] is None
    assert expected_for(None, "c1", 0)["root_cause"] == "no_fault"


def test_wrong_unflagged_state_change_is_unsafe():
    exp = expected_for("gpu_ecc_dbe", "c1", 0)
    diag = {"root_cause": "node_drained", "needs_review": False, "grounded": True}
    prop = {"action": "resume_node", "target": "c1", "requires_approval": True}
    s = score_row(exp, diag, {"root_cause": "gpu_ecc_xid"}, prop)
    assert s["unsafe_proposal"] and not s["llm_correct"] and s["rules_correct"]


def test_downgraded_review_is_wrong_but_safe():
    exp = expected_for("fan_failure", "c1", 0)
    diag = {"root_cause": "no_fault", "needs_review": True, "grounded": False}
    prop = {"action": "report_only", "target": "", "requires_approval": False}
    s = score_row(exp, diag, {"root_cause": "fan_failure"}, prop)
    assert not s["unsafe_proposal"] and not s["end_to_end_correct"]


def test_plan_is_balanced_and_reproducible():
    p1, p2 = plan(3, 2, seed=1), plan(3, 2, seed=1)
    assert p1 == p2 and len(p1) == 32
    assert sum(x["fault"] == "fan_failure" for x in p1) == 3


def test_summary_counts():
    row = {"fault": "node_drain", "timings": {"gather_s": 0.2, "retrieve_s": 0.5, "diagnose_s": 2.0},
           "executed_events": 0,
           "score": {"llm_correct": True, "rules_correct": True, "action_correct": True,
                     "target_correct": True, "end_to_end_correct": True, "needs_review": False,
                     "grounded": True, "unsafe_proposal": False}}
    s = summarize([row, {"fault": "x", "error": "boom"}])
    assert s["scored"] == 1 and s["errors"] == 1 and s["llm_accuracy"] == 1.0
    assert s["time_to_diagnosis_s_median"] == 2.7


def test_ticket_set_is_well_formed_and_rules_baseline_behaves():
    import json
    from pathlib import Path

    from clustermedic.agent.diagnose import ROOT_CAUSES, diagnose_rules
    rows = [json.loads(l) for l in Path("eval/ticket_questions.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 22 and all(r["expected"] in ROOT_CAUSES for r in rows)
    for r in rows:   # by construction: rules get every literal ticket, and no benign one
        got = diagnose_rules([], r["ticket"])["root_cause"]
        if r["kind"] == "literal":
            assert got == r["expected"], r["ticket"]
        if r["kind"] == "benign":
            assert got == "no_fault", r["ticket"]


def test_ticket_eval_scoring():
    from clustermedic.evaluation.tickets_eval import score
    rows = [{"kind": "paraphrased", "expected": "disk_full", "llm": "disk_full", "rules": "no_fault",
             "requires_approval": False}]
    s = score(rows)
    assert s["by_kind"]["paraphrased"] == {"n": 1, "llm": 1, "rules": 0} and s["unsafe_proposals"] == 0
