"""Guardrails that do not depend on the model behaving.

- mask_secrets: scrub credentials from anything we log, store, or post to a ticket.
- injection_signals: flag ticket text that tries to give the agent instructions.
  Flagging never changes the diagnosis (that rests on monitoring evidence). It is recorded in
  the audit log and shown to the human at the approval step and in the handover.
"""
import re

_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED GITHUB TOKEN]"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED AWS KEY ID]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED API KEY]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{16,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(MUNGE[_ ]?KEY\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


_INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules|prompts?)",
    r"disregard (the |all |your )?(previous |prior )?(instructions|rules|system)",
    r"\byou are now\b|\bact as\b|\bpretend to be\b",
    r"\bsystem prompt\b|\bdeveloper mode\b|\bjailbreak\b",
    r"\b(root_cause|confidence|needs_review|grounded)\b\s*(is|=|:)",
    r"\b(say|answer|respond|output|reply)\b.{0,40}\b(no_fault|root[_ ]cause)\b",
    r"\b(approve|auto[- ]?approve|skip (the )?approval|without approval)\b",
    r"\b(rm -rf|scancel|scontrol update|shutdown|reboot|curl .*\|\s*(ba)?sh)\b",
    r"</?ticket>",
]


def injection_signals(text: str) -> list[str]:
    """Return the patterns that matched (empty list = looks like an ordinary report)."""
    t = (text or "").lower()
    return [p for p in _INJECTION_PATTERNS if re.search(p, t)]
