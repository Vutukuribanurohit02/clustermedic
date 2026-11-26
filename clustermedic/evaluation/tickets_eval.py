"""Ticket-only evaluation: faults our monitoring cannot see (disk, munge, MTU), described by users.

Runs on a HEALTHY cluster. For each pre-registered ticket, compare the LLM's triage hint with the
rules baseline (which gets the same ticket text). Reports accuracy by ticket kind:
literal (contains the rules' keywords), paraphrased (does not), benign (should be no_fault).
"""
import json
from collections import defaultdict
from pathlib import Path

from clustermedic.agent import evidence
from clustermedic.agent.actions import propose
from clustermedic.agent.diagnose import diagnose_llm, diagnose_rules
from clustermedic.agent import llm

REPO = Path(__file__).resolve().parents[2]
TICKETS = REPO / "eval/ticket_questions.jsonl"


def score(rows: list[dict]) -> dict:
    by = defaultdict(lambda: {"n": 0, "llm": 0, "rules": 0})
    unsafe = 0
    for r in rows:
        b = by[r["kind"]]
        b["n"] += 1
        b["llm"] += r["llm"] == r["expected"]
        b["rules"] += r["rules"] == r["expected"]
        unsafe += r["requires_approval"]
    return {"by_kind": dict(by), "unsafe_proposals": unsafe, "n": len(rows)}


def to_markdown(s: dict, model: str) -> str:
    lines = [f"## Ticket-only triage (pre-registered set, {s['n']} tickets, model {model})",
             "| Ticket kind | n | LLM correct | Rules correct |", "|---|---|---|---|"]
    tot = {"n": 0, "llm": 0, "rules": 0}
    for kind in ("literal", "paraphrased", "benign"):
        b = s["by_kind"].get(kind, {"n": 0, "llm": 0, "rules": 0})
        lines.append(f"| {kind} | {b['n']} | {b['llm']} | {b['rules']} |")
        for k in tot:
            tot[k] += b[k]
    lines.append(f"| **all** | {tot['n']} | {tot['llm']} | {tot['rules']} |")
    lines.append(f"\nState-changing actions proposed: {s['unsafe_proposals']} (expected 0: ticket-only "
                 "diagnoses are always needs_review -> report_only)")
    return "\n".join(lines)


def run(retriever=None, quiet: bool = False) -> dict | None:
    from clustermedic.rag.__main__ import _retriever
    if evidence.anomalies(evidence.gather()):
        print("cluster is not healthy; clear faults first (ticket-only eval needs no anomalies)")
        return None
    retriever = retriever or _retriever("hybrid")
    rows = []
    for line in TICKETS.read_text().splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        d = diagnose_llm(t["ticket"], [], retriever.search(t["ticket"], k=4))
        r = diagnose_rules([], t["ticket"])
        p = propose(d, [])
        rows.append({**t, "llm": d["root_cause"], "rules": r["root_cause"],
                     "confidence": d["confidence"], "requires_approval": p["requires_approval"],
                     "seconds": d["seconds"]})
        mark = lambda x: "ok " if x == t["expected"] else "XX "
        if not quiet:
            print(f"{t['kind']:11} llm={mark(d['root_cause'])}{d['root_cause']:18} "
                  f"rules={mark(r['root_cause'])}{r['root_cause']:18} :: {t['ticket'][:60]}")
    s = score(rows)
    s["seconds"] = [r["seconds"] for r in rows]
    out = REPO / f"data/eval/tickets-{llm.current_model().replace(':', '_')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    if not quiet:
        print("\n" + to_markdown(s, llm.current_model()))
    return s
