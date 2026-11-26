"""GitHub Issues as the ticketing system, through the `gh` CLI (already authenticated).

Using gh means the agent never handles a GitHub token itself. Everything posted is passed
through mask_secrets first.
"""
import json
import os
import subprocess

from clustermedic.agent.guardrails import mask_secrets

LABEL = "clustermedic"
REPO = os.getenv("CLUSTERMEDIC_GH_REPO")  # e.g. "you/clustermedic"; default: repo of the cwd


class TicketError(RuntimeError):
    pass


def _gh(*args: str) -> str:
    cmd = ["gh", *args] + (["--repo", REPO] if REPO and args[0] in {"issue", "label"} else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise TicketError(f"gh {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def ensure_label() -> None:
    try:
        _gh("label", "create", LABEL, "--color", "B60205", "--description",
            "Opened by ClusterMedic", "--force")
    except TicketError:
        pass  # label creation is a nicety; issues still work without it


def open_issue(title: str, body: str) -> dict:
    ensure_label()
    url = _gh("issue", "create", "--title", mask_secrets(title)[:200],
              "--body", mask_secrets(body), "--label", LABEL)
    return {"url": url, "number": int(url.rstrip("/").split("/")[-1])}


def comment(number: int, body: str) -> None:
    _gh("issue", "comment", str(number), "--body", mask_secrets(body))


def close(number: int, reason: str = "completed") -> None:
    _gh("issue", "close", str(number), "--reason", reason)


def read_issue(number: int) -> dict:
    """Fetch an issue's title and body to use as the ticket text (untrusted user input)."""
    data = json.loads(_gh("issue", "view", str(number), "--json", "number,title,body,url"))
    return data


def list_open() -> list[dict]:
    return json.loads(_gh("issue", "list", "--label", LABEL, "--state", "open",
                          "--json", "number,title,createdAt,url"))
