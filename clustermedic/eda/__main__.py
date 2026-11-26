"""CLI:
  python -m clustermedic.eda diagnose <run_dir>      triage one flow run
  python -m clustermedic.eda eval [eda/runs]          score LLM vs rules on labelled runs
"""
import argparse
import json
from pathlib import Path

from clustermedic.agent.guardrails import mask_secrets
from clustermedic.rag.store import BM25Retriever

from . import evidence
from .diagnose import diagnose_llm, diagnose_rules

REPO = Path(__file__).resolve().parents[2]
EDA_RUNBOOKS = REPO / "runbooks/eda"


def _retriever():
    # Keyword retrieval: EDA evidence is full of exact tokens (VIOLATED, GPL-, latch) where
    # BM25 measured strongest in the cluster retrieval eval.
    return BM25Retriever(EDA_RUNBOOKS, pattern="ED-*.md")


def triage(run: Path, retriever=None) -> dict:
    run = Path(run)
    if not run.is_dir() or not any(f.is_file() for f in run.rglob("*")):
        # no logs/reports means "unknown", never "no_issue"
        raise SystemExit(f"{run}: no log or report files found; refusing to report 'no_issue'")
    ev = evidence.gather(run)
    found = evidence.anomalies(ev)
    chunks = (retriever or _retriever()).search("\n".join(found), k=4) if found else []
    return {"evidence": ev, "anomalies": found, "retrieved": [c["id"] for c in chunks],
            "rules": diagnose_rules(found), "diagnosis": diagnose_llm(ev, found, chunks)}


def report(t: dict) -> str:
    d = t["diagnosis"]
    lines = [f"# EDA triage: {Path(t['evidence']['run']).name}",
             f"Timing source: {t['evidence']['sta_source'] or '(none)'}",
             "Anomalies:", *[f"- {a}" for a in t["anomalies"] or ["(none)"]],
             f"Retrieved: {', '.join(t['retrieved']) or '-'}",
             f"Diagnosis: {d['root_cause']} at {d.get('location') or '-'} "
             f"(confidence {d['confidence']}, grounded {d['grounded']}, runbook {d['runbook']})",
             f"Rules baseline: {t['rules']['root_cause']}",
             f"Explanation: {d.get('explanation', '')}",
             "Evidence-based fixes:", *[f"- {x}" for x in d["evidence_based_fixes"] or ["(none)"]],
             "Model-suggested fixes (review before use):",
             *[f"- {x}" for x in d.get("recommended_fixes", []) or ["(none)"]],
             f"Diagnose time: {d['seconds']} s"]
    return mask_secrets("\n".join(lines))


def evaluate(runs_dir: Path) -> None:
    labels = json.loads((runs_dir / "labels.json").read_text())
    retriever = _retriever()
    rows = []
    for name, expected in labels.items():
        run = runs_dir / name
        if not run.exists():
            print(f"{name:16} MISSING run directory")
            continue
        t = triage(run, retriever)
        llm, rules = t["diagnosis"]["root_cause"], t["rules"]["root_cause"]
        symptom = bool(t["anomalies"]) or expected == "no_issue"
        rows.append({"run": name, "expected": expected, "llm": llm, "rules": rules,
                     "symptom_present": symptom, "grounded": t["diagnosis"]["grounded"],
                     "seconds": t["diagnosis"]["seconds"], "anomalies": t["anomalies"]})
        flag = "" if symptom else "  (symptom absent: excluded)"
        print(f"{name:16} expected={expected:18} llm={llm:18} rules={rules:18}{flag}")
        if symptom and (llm != expected or rules != expected):
            for a in t["anomalies"][:3]:
                print(f"{'':18}evidence: {a[:150]}")
    scored = [r for r in rows if r["symptom_present"]]
    n = len(scored)
    if n:
        print(f"\nscored {n}/{len(rows)} runs: LLM {sum(r['llm'] == r['expected'] for r in scored)}/{n}, "
              f"rules {sum(r['rules'] == r['expected'] for r in scored)}/{n}, "
              f"ungrounded LLM answers {sum(not r['grounded'] for r in scored)}")
    (runs_dir / "eval-results.json").write_text(json.dumps(rows, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.eda")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnose")
    d.add_argument("run")
    d.add_argument("--json", action="store_true")
    e = sub.add_parser("eval")
    e.add_argument("runs", nargs="?", default=str(REPO / "eda/runs"))
    a = p.parse_args(argv)
    if a.cmd == "diagnose":
        t = triage(Path(a.run))
        print(json.dumps(t, indent=2, default=str) if a.json else report(t))
    else:
        evaluate(Path(a.runs))


if __name__ == "__main__":
    main()
