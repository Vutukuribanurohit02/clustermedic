"""CLI: python -m clustermedic.faults {list,inject,clear,status}"""
import argparse
import json
import secrets
from datetime import datetime, timezone

from .backends import REPO
from .registry import FAULTS

LOG = REPO / "eval/injections.jsonl"          # ground truth (append-only)
ACTIVE = REPO / "eval/.active_faults.json"    # what is currently broken, for clearing


def _active() -> dict:
    return json.loads(ACTIVE.read_text()) if ACTIVE.exists() else {}


def _save_active(a: dict) -> None:
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(json.dumps(a, indent=2))


def cmd_list(_):
    for f in FAULTS.values():
        print(f"{f.name:15} target={f.target:4} root_cause={f.root_cause:14} {f.runbook}  {f.description}")


def cmd_inject(a):
    f = FAULTS[a.fault]
    ctx = {"node": a.node, "gpu": a.gpu}
    undo = f.inject(ctx)
    fid = f"inj-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    record = {"id": fid, "ts": datetime.now(timezone.utc).isoformat(), "fault": f.name,
              "target": f.target, "node": a.node if f.target != "bmc" else "bmc",
              "gpu": a.gpu if f.target == "gpu" else None,
              "root_cause": f.root_cause, "runbook": f.runbook}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    active = _active()
    active[fid] = {"fault": f.name, "undo": undo}
    _save_active(active)
    print(f"injected {f.name} -> {fid}")


def cmd_clear(a):
    active = _active()
    ids = list(active) if a.all else [a.id]
    for fid in ids:
        entry = active.pop(fid, None)
        if entry is None:
            print(f"unknown id {fid}")
            continue
        FAULTS[entry["fault"]].clear(entry["undo"])
        print(f"cleared {entry['fault']} ({fid})")
    _save_active(active)


def cmd_status(_):
    active = _active()
    print(json.dumps(active, indent=2) if active else "no active faults")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.faults")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    i = sub.add_parser("inject")
    i.add_argument("fault", choices=FAULTS)
    i.add_argument("--node", default="c1", choices=["c1", "c2"])
    i.add_argument("--gpu", default=0, type=int, choices=[0, 1])
    i.set_defaults(fn=cmd_inject)
    c = sub.add_parser("clear")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("id", nargs="?")
    g.add_argument("--all", action="store_true")
    c.set_defaults(fn=cmd_clear)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
