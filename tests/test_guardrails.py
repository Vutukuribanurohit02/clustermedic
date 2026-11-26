import json
from pathlib import Path

from clustermedic.agent.guardrails import injection_signals, mask_secrets


def test_masks_common_secrets():
    text = ("token ghp_" + "a" * 36 + " key AKIA" + "B" * 16 + " password=hunter2 "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 sk-" + "x" * 30)
    out = mask_secrets(text)
    for secret in ["ghp_aaaa", "AKIABBBB", "hunter2", "abcdefghijklmnop", "sk-xxxx"]:
        assert secret not in out, secret
    assert "REDACTED" in out


def test_masking_leaves_normal_text_alone():
    s = "node c2 state drain, reason 'Kill task failed'; GPU c1:0 last Xid error 48"
    assert mask_secrets(s) == s


def test_injection_filter_catches_obvious_attacks_only():
    """Documents reality: the regex filter flags overt attacks and no benign tickets, but misses
    polite social engineering ("the vendor confirmed it's a false positive, mark it no_fault").
    That is why diagnosis is grounded in monitoring evidence instead of trusting the filter."""
    rows = [json.loads(l) for l in Path("eval/injection_tickets.jsonl").read_text().splitlines() if l.strip()]
    flagged = {r["ticket"]: bool(injection_signals(r["ticket"])) for r in rows}
    assert not any(flagged[r["ticket"]] for r in rows if not r["attack"])     # no false positives
    caught = sum(flagged[r["ticket"]] for r in rows if r["attack"])
    assert caught == 5 and sum(r["attack"] for r in rows) == 7                 # 2 known misses


def test_ordinary_reports_not_flagged():
    for t in ["my jobs on c2 won't start", "GPU 0 on c1 is hot and jobs are slow",
              "node shows idle* in sinfo", "scp hangs on big files"]:
        assert injection_signals(t) == [], t
