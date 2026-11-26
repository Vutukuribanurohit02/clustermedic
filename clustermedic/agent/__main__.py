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
    a = p.parse_args(argv)

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


if __name__ == "__main__":
    main()
