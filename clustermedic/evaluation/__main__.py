"""CLI: python -m clustermedic.evaluation {run [--per-fault N] [--healthy N] [--seed S], tickets}"""
import argparse

from .harness import run


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.evaluation")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--per-fault", type=int, default=3)
    r.add_argument("--healthy", type=int, default=3, help="healthy control incidents (nothing injected)")
    r.add_argument("--seed", type=int, default=7)
    sub.add_parser("tickets", help="ticket-only triage eval (healthy cluster needed)")
    a = p.parse_args(argv)
    if a.cmd == "tickets":
        from .tickets_eval import run as run_tickets
        return run_tickets()
    run(a.per_fault, a.healthy, a.seed)


if __name__ == "__main__":
    main()
