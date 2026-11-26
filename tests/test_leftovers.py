from clustermedic.agent import actions
from clustermedic.evaluation import harness


def test_eval_flag_nested(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "OUT_DIR", tmp_path)
    flag = tmp_path / ".running"
    with harness.eval_running():
        with harness.eval_running():          # e.g. compare -> harness.run
            assert flag.exists()
        assert flag.exists()                  # inner exit must not remove it
    assert not flag.exists()


def _no_commands(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(actions, "_run", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(actions, "AUDIT_LOG", tmp_path / "audit.jsonl")
    return calls


def test_resume_is_noop_when_healthy(monkeypatch, tmp_path):
    calls = _no_commands(monkeypatch, tmp_path)
    monkeypatch.setattr(actions, "_node_state", lambda n: "idle")
    actions._resume("c1")
    assert calls == [] and "action_noop" in (tmp_path / "audit.jsonl").read_text()


def test_resume_runs_when_drained(monkeypatch, tmp_path):
    calls = _no_commands(monkeypatch, tmp_path)
    monkeypatch.setattr(actions, "_node_state", lambda n: "drain")
    actions._resume("c1")
    assert len(calls) == 1 and "state=resume" in calls[0]


def test_drain_keeps_existing_reason(monkeypatch, tmp_path):
    calls = _no_commands(monkeypatch, tmp_path)
    monkeypatch.setattr(actions, "_node_state", lambda n: "drain")
    actions._drain("c1:gpu0")
    assert calls == []
