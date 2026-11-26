"""Alert service tests: no Docker, no LLM, no network beyond localhost."""
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
import requests
from prometheus_client import CollectorRegistry, generate_latest

from clustermedic import serve
from clustermedic.agent import evidence

FIRING = {"alerts": [{"status": "firing", "labels": {"alertname": "ClusterAnomaly"},
                      "annotations": {"summary": "Health checks report 1 anomaly line(s)"}}]}


@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr(serve, "EVAL_FLAG", tmp_path / ".running")
    monkeypatch.setattr(serve, "INCIDENT_LOG", tmp_path / "incidents.jsonl")
    s = serve.Service(github=False)
    started = []
    monkeypatch.setattr(s, "_start", lambda ticket: started.append(ticket))
    return s, started, tmp_path


def test_alert_starts_one_incident_then_ignores_duplicates(svc):
    s, started, _ = svc
    assert s.on_alert(FIRING) == "incident started"
    time.sleep(0.05)
    assert s.on_alert(FIRING).startswith("ignored: an incident is already")
    assert len(started) == 1 and "ClusterAnomaly" in started[0]


def test_resolved_only_and_eval_flag_and_cooldown(svc):
    s, started, tmp = svc
    assert s.on_alert({"alerts": [{"status": "resolved"}]}) == "nothing firing"
    (tmp / ".running").touch()
    assert s.on_alert(FIRING).startswith("ignored: evaluation")
    (tmp / ".running").unlink()
    s.cooldown_until = time.time() + 60
    assert s.on_alert(FIRING).startswith("ignored: cooldown")
    assert started == []


def test_metrics_include_health_and_kpis(svc, monkeypatch):
    s, _, tmp = svc
    monkeypatch.setattr(evidence, "gather", lambda: {
        "nodes": [{"node": "c1", "healthy": True, "responding": True},
                  {"node": "c2", "healthy": False, "responding": False}],
        "pending_jobs": [], "tool_errors": {},
        "bmc_thermal": {"1U": {"temperatures": [{"name": "CPU1 Temp", "celsius": 41, "reporting": True},
                                                {"name": "CPU2 Temp", "celsius": None, "reporting": False}],
                               "fans": [{"name": "Fan", "reading": 2100, "reporting": True}]}}})
    monkeypatch.setattr(evidence, "anomalies", lambda ev: ["node c2 not responding"])
    (tmp / "incidents.jsonl").write_text(json.dumps({
        "root_cause": "node_drained", "action": "resume_node", "outcome": "fix applied and verified",
        "source": "alert", "needs_review": False,
        "timings": {"gather_s": 0.2, "retrieve_s": 0.5, "diagnose_s": 2.3}}) + "\n")
    reg = CollectorRegistry()
    reg.register(serve.ClusterCollector(s))
    text = generate_latest(reg).decode()
    assert "clustermedic_anomalies 1.0" in text
    assert 'clustermedic_node_responding{node="c2"} 0.0' in text
    assert 'sensor="CPU2 Temp"' not in text            # disabled sensor not exported
    assert 'clustermedic_incidents{action="resume_node"' in text
    assert 'clustermedic_time_to_diagnosis_seconds{source="alert",stat="median"} 3.0' in text


def test_http_approve_requires_token(svc):
    s, _, _ = svc
    reg = CollectorRegistry()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(s, reg, token="secret"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert requests.get(f"{base}/healthz", timeout=5).json() == {"ok": True}
        assert requests.post(f"{base}/approve", json={"id": "x", "approve": True}, timeout=5).status_code == 403
        assert requests.get(f"{base}/pending", timeout=5).status_code == 403
        r = requests.post(f"{base}/approve", json={"id": "nope", "approve": True},
                          headers={"X-ClusterMedic-Token": "secret"}, timeout=5)
        assert r.status_code == 200 and "no pending incident" in r.json()["result"]
    finally:
        srv.shutdown()


def test_own_exporter_down_is_not_a_cluster_anomaly():
    ev = {"targets_down": [{"job": "clustermedic", "instance": "host.docker.internal:9500"},
                           {"job": "gpu", "instance": "gpu-exporter:9400"}], "tool_errors": {}}
    found = evidence.anomalies(ev)
    assert len(found) == 1 and "gpu" in found[0]
