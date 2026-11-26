"""CLI: python -m clustermedic.agent evidence"""
import argparse
import json

from .evidence import anomalies, gather


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evidence", help="gather evidence and list anomalies")
    e.add_argument("--json", action="store_true", help="also print the raw evidence")
    a = p.parse_args(argv)
    if a.cmd == "evidence":
        ev = gather()
        if a.json:
            print(json.dumps(ev, indent=2, default=str))
        found = anomalies(ev)
        print("anomalies:" if found else "no anomalies found")
        for line in found:
            print("  -", line)


if __name__ == "__main__":
    main()
