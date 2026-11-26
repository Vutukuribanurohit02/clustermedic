"""CLI: python -m clustermedic.agent {evidence,diagnose}"""
import argparse
import json

from .evidence import anomalies, gather


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evidence", help="gather evidence and list anomalies")
    e.add_argument("--json", action="store_true", help="also print the raw evidence")
    d = sub.add_parser("diagnose", help="evidence + retrieval + LLM diagnosis")
    d.add_argument("ticket", nargs="?", default="", help="ticket text (optional)")
    r = sub.add_parser("run", help="full triage: diagnose, propose, ask approval, act, summarize")
    r.add_argument("ticket", nargs="?", default="")
    r.add_argument("--dry-run", action="store_true", help="diagnose and propose only; never act")
    a = p.parse_args(argv)
    if a.cmd == "run":
        return run(a.ticket, a.dry_run)

    ev = gather()
    found = anomalies(ev)
    if a.cmd == "evidence":
        if a.json:
            print(json.dumps(ev, indent=2, default=str))
        print("anomalies:" if found else "no anomalies found")
        for line in found:
            print("  -", line)
        return

    from clustermedic.rag.__main__ import _retriever
    from .diagnose import diagnose_llm, diagnose_rules
    query = (a.ticket + "\n" + "\n".join(found)).strip()
    chunks = _retriever("hybrid").search(query, k=4) if query else []
    print("anomalies:", *(f"\n  - {x}" for x in found) or [" none"])
    print("retrieved:", ", ".join(c["id"] for c in chunks) or "none")
    print("rules baseline:", diagnose_rules(found))
    print("LLM diagnosis:")
    print(json.dumps(diagnose_llm(a.ticket, found, chunks), indent=2))


def run(ticket: str, dry_run: bool) -> None:
    import uuid

    from langgraph.types import Command

    from .actions import refresh_node_map
    from .graph import build_graph, pending_approval

    try:
        refresh_node_map()   # lab-only bookkeeping so a dead node can be restarted later
    except Exception as e:
        print(f"(node map refresh skipped: {e})")
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = graph.invoke({"ticket": ticket, "dry_run": dry_run}, config)
    pending = pending_approval(graph, config)
    while pending:
        d, p = pending["diagnosis"], pending["proposal"]
        print(f"\nDIAGNOSIS: {d['root_cause']} on {p['target']}  "
              f"(confidence {d['confidence']}, grounded {d['grounded']})")
        print(f"REASONING: {d['reasoning']}")
        print(f"PROPOSED:  {p['action']} -> {p['target']}\n           {p['description']}")
        answer = input("Approve this action? [y/N] ").strip().lower() == "y"
        state = graph.invoke(Command(resume=answer), config)
        pending = pending_approval(graph, config)
    print("\n" + state["summary"])


if __name__ == "__main__":
    main()
