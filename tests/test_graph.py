"""End-to-end graph tests with everything external faked (no Docker, no Ollama)."""
import pytest
from langgraph.types import Command

from clustermedic.agent import actions, diagnose, evidence, graph as g


class FakeRetriever:
    def search(self, q, k=4):
        return [{"id": "RB-001#fix", "runbook": "RB-001", "section": "Fix", "score": 1, "text": "x"}]


@pytest.fixture
def lab(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(evidence, "gather", lambda: {})
    monkeypatch.setattr(evidence, "anomalies", lambda ev: ["node c2 state drain, reason 'Kill task failed'"])
    monkeypatch.setattr(diagnose, "chat_json", lambda *a, **k: {
        "root_cause": "node_drained", "target": "node c2", "confidence": 0.9,
        "evidence": ["node c2 state drain"], "reasoning": "drained"})
    monkeypatch.setattr(actions, "AUDIT_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(g, "INCIDENTS", tmp_path / "incidents")
    fake = actions.Action("resume_node", "resume", True, lambda t: calls.append(t), lambda t: True, "node")
    monkeypatch.setitem(actions.ACTIONS, "resume_node", fake)
    return calls, tmp_path


def _run(answer, dry_run=False):
    graph = g.build_graph(retriever=FakeRetriever())
    cfg = {"configurable": {"thread_id": "t"}}
    graph.invoke({"ticket": "jobs won't start", "dry_run": dry_run}, cfg)
    pending = g.pending_approval(graph, cfg)
    if pending is None:
        return None, graph.get_state(cfg).values
    state = graph.invoke(Command(resume=answer), cfg)
    return pending, state


def test_graph_pauses_and_acts_only_after_approval(lab):
    calls, tmp = lab
    pending, state = _run(True)
    assert pending["proposal"] == {"action": "resume_node", "target": "c2",
                                   "description": actions.ACTIONS["resume_node"].description,
                                   "requires_approval": True}
    assert calls == ["c2"] and state["result"]["verified"] is True
    assert "fix applied and verified" in state["summary"]
    audit = (tmp / "audit.jsonl").read_text()
    assert '"event": "proposed"' in audit and '"event": "approved"' in audit and '"event": "executed"' in audit


def test_denied_means_nothing_changes(lab):
    calls, _ = lab
    _, state = _run(False)
    assert calls == [] and "DENIED" in state["summary"]


def test_dry_run_never_pauses_or_acts(lab):
    calls, _ = lab
    pending, state = _run(True, dry_run=True)
    assert pending is None and calls == [] and "dry run" in state["summary"]


def test_low_trust_diagnosis_downgraded_to_report_only():
    p = actions.propose({"root_cause": "node_drained", "target": "c2", "needs_review": True}, [])
    assert p["action"] == "report_only" and p["requires_approval"] is False


def test_target_normalisation():
    an = ["GPU c2:1 last Xid error 79"]
    assert actions.normalise_target("gpu_ecc_xid", "the GPU", an) == "c2:1"
    assert actions.normalise_target("fan_failure", "BMC 1U: fan 'X' reading 0", []) == "bmc"
    assert actions.normalise_target("node_drained", "node c2", []) == "c2"
