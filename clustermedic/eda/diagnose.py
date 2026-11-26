"""EDA diagnosis: rules baseline + grounded LLM explanation + evidence-specific recommendations.

Same guardrails as the cluster agent: fixed root-cause list (schema enum), evidence-grounding
check, and the output is advice only (no automated edits to RTL, SDC or flow config).
"""
import re
import time

from clustermedic.agent.diagnose import _normalise_confidence
from clustermedic.agent.llm import chat_json

CAUSES = {
    "placement_density": "ED-006", "multiple_drivers": "ED-005", "undriven_net": "ED-004",
    "latch_inferred": "ED-003", "setup_violation": "ED-001", "hold_violation": "ED-002",
    "drc_violations": "ED-007", "flow_error": "ED-008", "no_issue": None,
}

# first match wins: upstream (synthesis/placement) problems before downstream symptoms
RULES = [
    (r"flow error \[GPL-|utilization|density", "placement_density"),
    (r"multiple conflicting drivers", "multiple_drivers"),
    (r"is used but has no driver", "undriven_net"),
    (r"latch inferred", "latch_inferred"),
    (r"^setup timing violated", "setup_violation"),
    (r"^hold timing violated", "hold_violation"),
    (r"^DRC: \d+ violations", "drc_violations"),
    (r"^flow error", "flow_error"),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string", "enum": list(CAUSES)},
        "location": {"type": "string", "description": "signal, path or stage the problem is in"},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
        "recommended_fixes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["root_cause", "location", "confidence", "evidence", "explanation", "recommended_fixes"],
}

SYSTEM = """You are a senior physical-design and verification engineer reviewing a chip-design flow run
(Yosys synthesis, OpenROAD place and route, OpenSTA timing). Using ONLY the anomaly lines and the
runbook excerpts, decide the single most important ROOT CAUSE and explain it to a junior engineer.
Rules:
- Pick a root cause only if an anomaly line shows it. Runbook text is guidance, not evidence.
- Synthesis problems (multiple drivers, undriven nets, latches) and placement failures come before
  timing or DRC symptoms they may cause.
- Recommended fixes must be specific to the evidence (name the path, signal or stage) and ordered
  from least to most invasive. Do not invent numbers that are not in the evidence.
- Lines starting with "note:" are informational and are never a root cause.
- If there are no anomalies, answer "no_issue". confidence is between 0 and 1."""


def diagnose_rules(anomalies: list[str]) -> dict:
    for pattern, cause in RULES:
        if any(re.search(pattern, a, re.I | re.M) for a in anomalies):
            return {"root_cause": cause, "runbook": CAUSES[cause]}
    return {"root_cause": "no_issue", "runbook": None}


def _problems(anomalies: list[str]) -> list[str]:
    return [a for a in anomalies if not a.startswith("note:")]


def is_grounded(cause: str, anomalies: list[str]) -> bool:
    if cause == "no_issue":
        return not _problems(anomalies)
    return any(re.search(p, a, re.I | re.M) for p, c in RULES if c == cause for a in anomalies)


def recommendations(cause: str, ev: dict) -> list[str]:
    """Deterministic, evidence-specific starting points (the LLM explains; this never guesses)."""
    paths = sorted((p for p in ev.get("paths", []) if p["violated"]), key=lambda p: p["slack"])
    w = paths[0] if paths else {}
    y = ev.get("yosys", {})
    if cause == "setup_violation":
        recs = [f"Check the constraint first: is the clock period in the SDC intended? Worst path "
                f"{w.get('startpoint')} -> {w.get('endpoint')} misses by {abs(w.get('slack', 0)):.3f} ns."]
        if (w.get("logic_levels") or 0) >= 10:
            recs.append(f"{w['logic_levels']} logic levels: restructure the logic or add a pipeline stage.")
        if (w.get("max_fanout") or 0) >= 16:
            recs.append(f"Max fanout {w['max_fanout']} on the path: buffer or duplicate the driver.")
        if w.get("weakest_cells"):
            recs.append(f"Weak drive cells on the path ({', '.join(w['weakest_cells'][:3])}): "
                        "allow sizing/repair_timing to upsize, or check DONT_USE settings.")
        recs.append("If the margin is small, try timing-driven placement/repair before changing RTL.")
        return recs
    if cause == "hold_violation":
        return [f"Hold path {w.get('startpoint')} -> {w.get('endpoint')} at {w.get('slack')} ns: "
                "run hold repair after CTS (insert delay buffers on the short path).",
                "Check clock skew between launch and capture flops; large skew causes hold failures."]
    if cause == "latch_inferred":
        return [f"Signal(s) {', '.join(y.get('latches', [])[:3])}: assign a value on every branch of the "
                "combinational always block, or add a default assignment at the top.",
                "If a latch is intended, document it and constrain it; otherwise use always_comb."]
    if cause == "undriven_net":
        return [f"Wire(s) {', '.join(y.get('undriven', [])[:3])} are read but never driven: connect the "
                "driver or remove the read; check port name typos and missing instance connections.",
                "Enable implicit-net checks (`default_nettype none`) to catch this at elaboration."]
    if cause == "multiple_drivers":
        return [f"Signal(s) {', '.join(y.get('multiple_drivers', [])[:3])} are driven from more than one "
                "place: keep a single driver (one always block / one assign) or add a mux."]
    if cause == "placement_density":
        return ["Placement could not fit the cells: lower CORE_UTILIZATION or enlarge the die/core area.",
                "Raise PLACE_DENSITY only if utilization is reasonable; check for macros blocking rows."]
    if cause == "drc_violations":
        d = ev.get("drc", {})
        return [f"{d.get('total')} DRC violations, mostly {', '.join(list(d.get('by_type', {}))[:2]) or 'see report'}: "
                "inspect the hot spots in the GUI first.",
                "Congestion-driven DRCs: lower utilization or routing density, add routing layers, "
                "or spread cells in the congested region."]
    if cause == "flow_error":
        return [f"Fix the first error: {ev['errors'][0]['code']} {ev['errors'][0]['message'][:100]}"
                if ev.get("errors") else "Read the first [ERROR] line in the logs."]
    return []


def build_prompt(anomalies: list[str], chunks: list[dict]) -> str:
    a = "\n".join(f"- {x}" for x in anomalies) or "- (none)"
    rb = "\n\n".join(f"[{c['id']}]\n{c['text'][:700]}" for c in chunks)
    return (f"Anomalies found in the flow run:\n{a}\n\nRunbook excerpts:\n{rb}\n\n"
            f"Allowed root causes: {', '.join(CAUSES)}")


def diagnose_llm(ev: dict, anomalies: list[str], chunks: list[dict]) -> dict:
    t0 = time.time()
    if not _problems(anomalies):
        out = {"root_cause": "no_issue", "location": "", "confidence": 1.0, "evidence": [],
               "explanation": "No timing, DRC, synthesis or flow errors were found.",
               "recommended_fixes": []}
    else:
        out = chat_json(SYSTEM, build_prompt(anomalies, chunks), SCHEMA)
        if out.get("root_cause") not in CAUSES:
            out["root_cause"] = "no_issue"
        out["confidence"] = _normalise_confidence(out.get("confidence"))
    out["runbook"] = CAUSES[out["root_cause"]]
    out["grounded"] = is_grounded(out["root_cause"], anomalies)
    if not out["grounded"]:
        out["confidence"] = min(out["confidence"], 0.3)
    out["needs_review"] = (not out["grounded"]) or out["confidence"] < 0.6
    out["evidence_based_fixes"] = recommendations(out["root_cause"], ev) if out["grounded"] else []
    out["seconds"] = round(time.time() - t0, 1)
    return out
