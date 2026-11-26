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
    c = sub.add_parser("compare", help="compare chat models on the same evals")
    c.add_argument("--models", nargs="+", required=True)
    c.add_argument("--incidents", type=int, default=0,
                   help="also run the end-to-end eval with N incidents per fault (slow)")
    a = p.parse_args(argv)
    if a.cmd == "compare":
        from .compare import run as run_compare
        return run_compare(a.models, a.incidents)
    if a.cmd == "tickets":
        from .tickets_eval import run as run_tickets
        return run_tickets()
    run(a.per_fault, a.healthy, a.seed)


if __name__ == "__main__":
    main()
