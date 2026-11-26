"""Compare chat models on the same pre-registered evals.

For each model: ticket-only triage (22 tickets), prompt injection (8 tickets against an active
fan_failure), and optionally the end-to-end fault-injection eval. Same retriever, prompts,
guardrails and temperature 0, so only the model differs.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import requests

from clustermedic.agent import evidence, llm

from . import injection_eval, tickets_eval
from .harness import faults_cli, log, wait_quiet, wait_until

REPO = Path(__file__).resolve().parents[2]


def installed_models() -> set[str]:
    tags = requests.get(f"{llm.OLLAMA_URL}/api/tags", timeout=10).json().get("models", [])
    return {m["name"] for m in tags} | {m["name"].removesuffix(":latest") for m in tags}


def model_size_gb(name: str) -> float | None:
    for m in requests.get(f"{llm.OLLAMA_URL}/api/tags", timeout=10).json().get("models", []):
        if m["name"] in (name, f"{name}:latest"):
            return round(m.get("size", 0) / 1e9, 1)
    return None


def run(models: list[str], incidents_per_fault: int = 0) -> Path:
    from .harness import eval_running
    with eval_running():          # fault injections here must not open real tickets
        return _run(models, incidents_per_fault)


def _run(models: list[str], incidents_per_fault: int = 0) -> Path:
    from clustermedic.rag.__main__ import _retriever
    have = installed_models()
    missing = [m for m in models if m not in have]
    if missing:
        raise SystemExit(f"not installed in Ollama: {missing}. In PowerShell: ollama pull <model>")
    retriever = _retriever("hybrid")
    faults_cli("clear", "--all")
    if not wait_quiet():
        raise SystemExit("cluster is not healthy; fix it before comparing models")

    results = {}
    for m in models:
        llm.set_model(m)
        log(f"=== {m}: warming up")
        t0 = time.time()
        llm.chat_json("Reply with JSON.", "Say ok.", {"type": "object", "properties": {"ok": {"type": "string"}}})
        cold_s = round(time.time() - t0, 1)

        log(f"{m}: ticket-only triage (22 tickets)")
        tk = tickets_eval.run(retriever, quiet=True)

        log(f"{m}: prompt injection (8 tickets, fan_failure active)")
        faults_cli("inject", "fan_failure")
        wait_until(lambda: bool(evidence.anomalies(evidence.gather())), timeout_s=60, interval_s=3)
        try:
            inj = injection_eval.run(retriever, quiet=True)
        finally:
            faults_cli("clear", "--all")
            wait_quiet()

        e2e = None
        if incidents_per_fault:
            from .harness import run as run_incidents
            log(f"{m}: end-to-end incidents ({incidents_per_fault} per fault)")
            stem = run_incidents(per_fault=incidents_per_fault, healthy=1)
            e2e = json.loads(Path(f"{stem}-summary.json").read_text())

        results[m] = {"size_gb": model_size_gb(m), "cold_load_s": cold_s, "tickets": tk,
                      "injection": inj, "e2e": e2e}
        bk = tk["by_kind"]
        log(f"{m}: tickets {sum(b['llm'] for b in bk.values())}/{tk['n']}, "
            f"paraphrased {bk['paraphrased']['llm']}/{bk['paraphrased']['n']}, "
            f"injection changed {inj['changed']}/{inj['n']}, unsafe {inj['unsafe']}")

    stamp = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    out = REPO / f"data/eval/compare-{stamp}"
    Path(f"{out}.json").write_text(json.dumps(results, indent=2))
    md = to_markdown(results)
    Path(f"{out}.md").write_text(md + "\n")
    print("\n" + md)
    return out


def to_markdown(results: dict) -> str:
    any_e2e = any(r["e2e"] for r in results.values())
    head = ["Model", "Size (GB)", "Tickets (22)", "Paraphrased (9)", "Benign correct (4)",
            "Injection: diagnosis changed (8)", "Injection: unsafe", "Median diagnose s (tickets)"]
    if any_e2e:
        head += ["E2E correct", "E2E unsafe"]
    lines = [f"## Model comparison ({datetime.now(timezone.utc):%Y-%m-%d}, same prompts/retriever/guardrails, temperature 0)",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for m, r in results.items():
        bk = r["tickets"]["by_kind"]
        row = [m, r["size_gb"], sum(b["llm"] for b in bk.values()), bk["paraphrased"]["llm"],
               bk["benign"]["llm"], r["injection"]["changed"], r["injection"]["unsafe"],
               round(median(r["tickets"]["seconds"]), 1)]
        if any_e2e:
            e = r["e2e"] or {}
            row += [e.get("end_to_end_accuracy", "-"), e.get("unsafe_proposals", "-")]
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)
