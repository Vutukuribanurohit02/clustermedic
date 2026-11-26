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
    r.add_argument("--issue", type=int, help="take the ticket text from this GitHub issue")
    r.add_argument("--github", action="store_true", help="open a GitHub issue for this incident")
    sub.add_parser("injection-eval", help="run the injection tickets against the current fault")
    sub.add_parser("pending", help="list alert incidents waiting for approval (service must run)")
    ap = sub.add_parser("approve", help="approve or deny a pending alert incident")
    ap.add_argument("id")
    ap.add_argument("--deny", action="store_true")
    a = p.parse_args(argv)
    if a.cmd in ("pending", "approve"):
        return service_call(a)
    if a.cmd == "run":
        return run(a.ticket, a.dry_run, a.issue, a.github)
    if a.cmd == "injection-eval":
        return injection_eval()

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


def service_call(a) -> None:
    import requests

    from clustermedic.serve import TOKEN_FILE
    headers = {"X-ClusterMedic-Token": TOKEN_FILE.read_text().strip()}
    base = "http://localhost:9500"
    if a.cmd == "pending":
        items = requests.get(f"{base}/pending", headers=headers, timeout=10).json()
        if not items:
            print("no incidents waiting for approval")
        for iid, it in items.items():
            print(f"{iid}  [{it['created']}]  {it['root_cause']} -> {it['action']} {it['target']}  "
                  f"(confidence {it['confidence']}, grounded {it['grounded']})")
            print(f"    {it['reasoning']}")
            if it.get("ticket_url"):
                print(f"    ticket: {it['ticket_url']}")
            print(f"    approve: python -m clustermedic.agent approve {iid}   "
                  f"deny: python -m clustermedic.agent approve {iid} --deny")
        return
    r = requests.post(f"{base}/approve", headers=headers, timeout=120,
                      json={"id": a.id, "approve": not a.deny})
    print(r.json())


def run(ticket: str, dry_run: bool, issue: int | None = None, github: bool = False) -> None:
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
    state = graph.invoke({"ticket": ticket, "dry_run": dry_run, "issue": issue,
                          "github": github}, config)
    pending = pending_approval(graph, config)
    while pending:
        d, p = pending["diagnosis"], pending["proposal"]
        print(f"\nDIAGNOSIS: {d['root_cause']} on {p['target']}  "
              f"(confidence {d['confidence']}, grounded {d['grounded']})")
        print(f"REASONING: {d['reasoning']}")
        print(f"PROPOSED:  {p['action']} -> {p['target']}\n           {p['description']}")
        if pending.get("injection"):
            print("WARNING:   the ticket contains instruction-like text; check it before approving.")
        answer = input("Approve this action? [y/N] ").strip().lower() == "y"
        state = graph.invoke(Command(resume=answer), config)
        pending = pending_approval(graph, config)
    print("\n" + state["summary"])
    if state.get("ticket_url"):
        print(f"\nTicket: {state['ticket_url']}")


def injection_eval() -> None:
    from clustermedic.evaluation.injection_eval import run as run_injection
    from clustermedic.rag.__main__ import _retriever
    run_injection(_retriever("hybrid"))


if __name__ == "__main__":
    main()
