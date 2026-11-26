"""CLI: python -m clustermedic.evaluation run [--per-fault N] [--healthy N] [--seed S]"""
import argparse

from .harness import run


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.evaluation")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--per-fault", type=int, default=3)
    r.add_argument("--healthy", type=int, default=3, help="healthy control incidents (nothing injected)")
    r.add_argument("--seed", type=int, default=7)
    a = p.parse_args(argv)
    run(a.per_fault, a.healthy, a.seed)


if __name__ == "__main__":
    main()
