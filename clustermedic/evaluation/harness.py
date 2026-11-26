"""Run the evaluation: for each planned incident, wait for a quiet cluster, inject a labelled
fault, wait until its symptom is visible, run the agent in DRY RUN, score, clear.

The agent never sees the ground truth: faults are injected through the injector CLI, and the
agent only observes the cluster.
"""
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from clustermedic.agent import evidence
from clustermedic.agent.actions import AUDIT_LOG
from clustermedic.agent import llm
from clustermedic.faults.registry import FAULTS

from .scoring import expected_for, score_row, summarize, to_markdown

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data/eval"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def faults_cli(*args: str) -> str:
    out = subprocess.run([sys.executable, "-m", "clustermedic.faults", *args],
                         capture_output=True, text=True, timeout=600, cwd=REPO)
    if out.returncode != 0:
        raise RuntimeError(f"faults {' '.join(args)}: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout.strip()


def wait_until(check, timeout_s: int, interval_s: int = 10) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if check():
            return True
        time.sleep(interval_s)
    return False


def quiet() -> bool:
    return not evidence.anomalies(evidence.gather())


def wait_quiet(timeout_s: int = 360) -> bool:
    """Two consecutive clean checks, so lingering metric windows (2m) have expired."""
    return wait_until(lambda: quiet() and (time.sleep(10) or quiet()), timeout_s)


def plan(per_fault: int, healthy: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    items = [{"fault": f, "node": rng.choice(["c1", "c2"]), "gpu": rng.choice([0, 1])}
             for f in FAULTS for _ in range(per_fault)]
    items += [{"fault": None, "node": "c1", "gpu": 0} for _ in range(healthy)]
    rng.shuffle(items)
    return items


def executed_count() -> int:
    if not AUDIT_LOG.exists():
        return 0
    return sum('"event": "executed"' in l for l in AUDIT_LOG.read_text().splitlines())


def run_one(graph, item: dict, idx: int) -> dict:
    fault, node, gpu = item["fault"], item["node"], item["gpu"]
    row = {"i": idx, **item, "expected": expected_for(fault, node, gpu)}
    if not wait_quiet():
        try:
            blocking = evidence.anomalies(evidence.gather())
        except Exception as e:
            blocking = [f"(could not read anomalies: {e})"]
        row["error"] = f"cluster did not become quiet before injection; blocking: {blocking}"
        return row
    try:
        if fault:
            faults_cli("inject", fault, "--node", node, "--gpu", str(gpu))
            # GPU/BMC symptoms appear after the next scrape or restart; wait until visible.
            if not wait_until(lambda: not quiet(), timeout_s=120, interval_s=5):
                row["error"] = "symptom never appeared"
                return row
        before = executed_count()
        state = graph.invoke({"ticket": "", "dry_run": True, "source": "eval"},
                             {"configurable": {"thread_id": f"eval-{idx}"}})
        row.update({
            "anomalies": state["anomalies"],
            "retrieved": [c["id"] for c in state.get("chunks", [])],
            "diagnosis": {k: state["diagnosis"].get(k) for k in
                          ("root_cause", "target", "confidence", "grounded", "needs_review", "reasoning")},
            "rules": state["rules"], "proposal": state["proposal"],
            "timings": state.get("timings", {}),
            "executed_events": executed_count() - before,
        })
        row["score"] = score_row(row["expected"], state["diagnosis"], state["rules"], state["proposal"])
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
    finally:
        if fault:
            try:
                faults_cli("clear", "--all")
            except Exception as e:
                row["clear_error"] = str(e)
    return row


def run(per_fault: int = 3, healthy: int = 3, seed: int = 7) -> Path:
    from clustermedic.agent.graph import build_graph
    from clustermedic.rag.__main__ import _retriever

    started = datetime.now(timezone.utc)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUT_DIR / f"run-{started:%Y%m%d-%H%M%S}"
    log(f"{len(plan(per_fault, healthy, seed))} incidents planned; results -> {stem}.jsonl")

    flag = OUT_DIR / ".running"           # tells the alert service to stand down
    flag.touch()
    try:
        return _run(per_fault, healthy, seed, started, stem)
    finally:
        flag.unlink(missing_ok=True)


def _run(per_fault, healthy, seed, started, stem):
    from clustermedic.agent.graph import build_graph
    from clustermedic.rag.__main__ import _retriever
    items = plan(per_fault, healthy, seed)
    faults_cli("clear", "--all")          # start clean
    graph = build_graph(retriever=_retriever("hybrid"))
    log("warming up the model (excluded from timings)")
    graph.invoke({"ticket": "warm-up", "dry_run": True, "source": "eval"},
                 {"configurable": {"thread_id": "warm"}})
    from clustermedic.agent.diagnose import diagnose_llm
    diagnose_llm("", ["node c1 state drain, reason 'warm-up'"], [])

    rows = []
    with open(f"{stem}.jsonl", "w") as fh:
        for i, item in enumerate(items, 1):
            row = run_one(graph, item, i)
            rows.append(row)
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            if row.get("error"):
                log(f"{i:>2}/{len(items)} {item['fault'] or 'healthy':14} ERROR {row['error']}")
            else:
                s = row["score"]
                log(f"{i:>2}/{len(items)} {item['fault'] or 'healthy':14} -> "
                    f"llm={row['diagnosis']['root_cause']:16} rules={row['rules']['root_cause']:16} "
                    f"action={row['proposal']['action']:17} {'OK ' if s['end_to_end_correct'] else 'MISS'}"
                    f"{' UNSAFE' if s['unsafe_proposal'] else ''}")
            if row.get("clear_error"):
                log(f"clear failed ({row['clear_error']}); stopping so later incidents are not contaminated")
                break

    s = summarize(rows)
    meta = {"started": f"{started:%Y-%m-%d %H:%M UTC}", "model": llm.current_model(), "per_fault": per_fault,
            "healthy": healthy, "seed": seed}
    md = to_markdown(s, meta)
    Path(f"{stem}-summary.md").write_text(md + "\n")
    Path(f"{stem}-summary.json").write_text(json.dumps({"meta": meta, **s}, indent=2))
    print("\n" + md)
    return stem
