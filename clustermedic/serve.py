"""ClusterMedic service: metrics exporter + Alertmanager webhook + approval queue.

    Prometheus --scrapes--> /metrics   (cluster health + KPIs from data/incidents.jsonl)
    Prometheus --alert rule--> Alertmanager --webhook--> /alert --> agent runs (LangGraph)
    agent pauses for approval --> `python -m clustermedic.agent pending / approve <id>`

Safety:
- One incident at a time; alerts are ignored while one is running/pending and for a cooldown after.
- Alerts are ignored while an evaluation run is in progress (data/eval/.running).
- /pending and /approve need a random token stored in data/serve.token (mode 600), so only
  someone on this machine can approve. /alert can only START a diagnosis, never approve one.
"""
import argparse
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
TOKEN_FILE = DATA / "serve.token"
INCIDENT_LOG = DATA / "incidents.jsonl"
EVAL_FLAG = DATA / "eval/.running"
COOLDOWN_S = 180


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- metrics

class ClusterCollector:
    """Computed at scrape time: live cluster health plus KPIs from the incident log."""

    def __init__(self, service: "Service"):
        self.service = service

    def collect(self):
        from clustermedic.agent import evidence
        ev = evidence.gather()
        found = evidence.anomalies(ev)

        g = GaugeMetricFamily("clustermedic_anomalies", "Anomaly lines found by the health checks")
        g.add_metric([], len(found))
        yield g

        healthy = GaugeMetricFamily("clustermedic_node_healthy", "1 if the Slurm node is usable", labels=["node"])
        resp = GaugeMetricFamily("clustermedic_node_responding", "1 if slurmd responds", labels=["node"])
        for n in ev.get("nodes", []):
            healthy.add_metric([n["node"]], int(n["healthy"]))
            resp.add_metric([n["node"]], int(n["responding"]))
        yield healthy
        yield resp

        pend = GaugeMetricFamily("clustermedic_pending_jobs", "Jobs pending in the queue")
        pend.add_metric([], len(ev.get("pending_jobs", [])))
        yield pend

        temp = GaugeMetricFamily("clustermedic_bmc_temperature_celsius", "BMC temperature",
                                 labels=["chassis", "sensor"])
        fan = GaugeMetricFamily("clustermedic_bmc_fan_rpm", "BMC fan speed", labels=["chassis", "fan"])
        for chassis, t in ev.get("bmc_thermal", {}).items():
            for s in t["temperatures"]:
                if s["reporting"]:
                    temp.add_metric([chassis, s["name"]], s["celsius"])
            for f in t["fans"]:
                if f["reporting"]:
                    fan.add_metric([chassis, f["name"]], f["reading"])
        yield temp
        yield fan

        errs = GaugeMetricFamily("clustermedic_tool_errors", "Health-check tools that failed")
        errs.add_metric([], len(ev.get("tool_errors", {})))
        yield errs

        yield from self._kpis()

        q = GaugeMetricFamily("clustermedic_pending_approvals", "Fixes waiting for a human")
        q.add_metric([], len(self.service.pending))
        yield q

    def _kpis(self):
        recs = []
        if INCIDENT_LOG.exists():
            recs = [json.loads(l) for l in INCIDENT_LOG.read_text().splitlines() if l.strip()]
        inc = GaugeMetricFamily("clustermedic_incidents", "Incidents handled (from incident log)",
                                labels=["root_cause", "action", "outcome", "source"])
        counts = {}
        for r in recs:
            k = (r["root_cause"], r["action"], r["outcome"], r.get("source", "cli"))
            counts[k] = counts.get(k, 0) + 1
        for k, v in counts.items():
            inc.add_metric(list(k), v)
        yield inc

        ttd = GaugeMetricFamily("clustermedic_time_to_diagnosis_seconds",
                                "Gather+retrieve+diagnose time", labels=["stat", "source"])
        by_src = {}
        for r in recs:
            t = r.get("timings", {})
            by_src.setdefault(r.get("source", "cli"), []).append(
                t.get("gather_s", 0) + t.get("retrieve_s", 0) + t.get("diagnose_s", 0))
        from statistics import median
        for src, xs in by_src.items():
            ttd.add_metric(["mean", src], sum(xs) / len(xs))
            ttd.add_metric(["median", src], median(xs))
            ttd.add_metric(["last", src], xs[-1])
        yield ttd

        rev = GaugeMetricFamily("clustermedic_needs_review", "Incidents flagged for human review",
                                labels=["source"])
        tot = {}
        for r in recs:
            tot[r.get("source", "cli")] = tot.get(r.get("source", "cli"), 0) + bool(r.get("needs_review"))
        for src, v in tot.items():
            rev.add_metric([src], v)
        yield rev


# ---------------------------------------------------------------- incident runner

class Service:
    def __init__(self, github: bool):
        self.github = github
        self.lock = threading.Lock()
        self.busy = False
        self.cooldown_until = 0.0
        self.pending: dict[str, dict] = {}
        self.graph = None

    def _graph(self):
        if self.graph is None:
            from clustermedic.agent.graph import build_graph
            self.graph = build_graph()
        return self.graph

    def on_alert(self, payload: dict) -> str:
        firing = [a for a in payload.get("alerts", []) if a.get("status") == "firing"]
        if not firing:
            return "nothing firing"
        if EVAL_FLAG.exists():
            return "ignored: evaluation run in progress"
        with self.lock:
            if self.busy or self.pending:
                return "ignored: an incident is already in progress"
            if time.time() < self.cooldown_until:
                return "ignored: cooldown after previous incident"
            self.busy = True
        names = sorted({a.get("labels", {}).get("alertname", "?") for a in firing})
        summaries = [a.get("annotations", {}).get("summary", "") for a in firing]
        ticket = f"Automated alert: {', '.join(names)}. {' '.join(s for s in summaries if s)}"
        threading.Thread(target=self._start, args=(ticket,), daemon=True).start()
        return "incident started"

    def _start(self, ticket: str) -> None:
        iid = f"inc-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        config = {"configurable": {"thread_id": iid}}
        try:
            from clustermedic.agent.actions import refresh_node_map
            from clustermedic.agent.graph import pending_approval
            try:
                refresh_node_map()
            except Exception as e:
                log(f"node map refresh skipped: {e}")
            log(f"{iid}: diagnosing ({ticket})")
            state = self._graph().invoke({"ticket": ticket, "github": self.github,
                                          "source": "alert"}, config)
            pending = pending_approval(self._graph(), config)
            if pending:
                d, p = pending["diagnosis"], pending["proposal"]
                self.pending[iid] = {"config": config, "created": datetime.now().isoformat(timespec="seconds"),
                                     "root_cause": d["root_cause"], "confidence": d["confidence"],
                                     "grounded": d["grounded"], "reasoning": d["reasoning"],
                                     "action": p["action"], "target": p["target"],
                                     "description": p["description"],
                                     "ticket_url": self._graph().get_state(config).values.get("ticket_url", "")}
                log(f"{iid}: awaiting approval: {p['action']} -> {p['target']} "
                    f"(run: python -m clustermedic.agent pending)")
            else:
                log(f"{iid}: finished: {state.get('outcome')}")
                self._finish()
        except Exception as e:
            log(f"{iid}: FAILED: {e}")
            self._finish()

    def decide(self, iid: str, approve: bool) -> str:
        item = self.pending.pop(iid, None)
        if item is None:
            return f"no pending incident {iid}"
        from langgraph.types import Command
        log(f"{iid}: {'APPROVED' if approve else 'DENIED'} by human")
        state = self._graph().invoke(Command(resume=approve), item["config"])
        log(f"{iid}: finished: {state.get('outcome')}")
        self._finish()
        return state.get("outcome", "done")

    def _finish(self) -> None:
        with self.lock:
            self.busy = False
            self.cooldown_until = time.time() + COOLDOWN_S


# ---------------------------------------------------------------- HTTP

def make_handler(service: Service, registry: CollectorRegistry, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console for incident logs
            pass

        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-ClusterMedic-Token", ""), token)

        def _json(self) -> dict:
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n > 1_000_000:
                raise ValueError("payload too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path == "/metrics":
                return self._send(200, generate_latest(registry), "text/plain; version=0.0.4")
            if self.path == "/healthz":
                return self._send(200, {"ok": True})
            if self.path == "/pending":
                if not self._authorised():
                    return self._send(403, {"error": "bad token"})
                return self._send(200, {k: {kk: vv for kk, vv in v.items() if kk != "config"}
                                        for k, v in service.pending.items()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = self._json()
            except Exception as e:
                return self._send(400, {"error": str(e)})
            if self.path == "/alert":
                msg = service.on_alert(body)
                log(f"alert received: {msg}")
                return self._send(200, {"result": msg})
            if self.path == "/approve":
                if not self._authorised():
                    return self._send(403, {"error": "bad token"})
                return self._send(200, {"result": service.decide(body.get("id", ""),
                                                                 body.get("approve") is True)})
            self._send(404, {"error": "not found"})

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.serve")
    p.add_argument("--port", type=int, default=9500)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--github", action="store_true", help="open GitHub issues for alert incidents")
    a = p.parse_args(argv)

    DATA.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token)
    os.chmod(TOKEN_FILE, 0o600)

    service = Service(github=a.github)
    registry = CollectorRegistry()
    registry.register(ClusterCollector(service))
    server = ThreadingHTTPServer((a.host, a.port), make_handler(service, registry, token))
    log(f"ClusterMedic service on :{a.port} (github={a.github}); approvals token in {TOKEN_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("stopping")


if __name__ == "__main__":
    main()
