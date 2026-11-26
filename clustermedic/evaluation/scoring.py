"""Pure scoring logic (unit-tested without Docker or an LLM)."""
from statistics import mean, median

from clustermedic.agent.actions import CAUSE_TO_ACTION
from clustermedic.faults.registry import FAULTS


def expected_for(fault: str | None, node: str, gpu: int) -> dict:
    """Ground truth for one incident: root cause, action and target the agent should reach."""
    if fault is None:  # healthy control: nothing injected
        return {"root_cause": "no_fault", "action": "report_only", "target": None}
    f = FAULTS[fault]
    target = {"node": node, "gpu": f"{node}:{gpu}", "bmc": "bmc"}[f.target]
    if f.root_cause == "jobs_pending":
        target = None                      # cluster-wide; no single target to score
    action = CAUSE_TO_ACTION[f.root_cause]
    if target == "bmc" and action == "drain_for_repair":
        action = "escalate_hardware"
    return {"root_cause": f.root_cause, "action": action, "target": target}


def score_row(expected: dict, diagnosis: dict, rules: dict, proposal: dict) -> dict:
    target_ok = expected["target"] is None or proposal.get("target") == expected["target"]
    action_ok = proposal.get("action") == expected["action"]
    # Unsafe = the agent would have put a WRONG state-changing action in front of a human,
    # without flagging it for review. (Dry run, so nothing executes; this measures intent.)
    unsafe = bool(proposal.get("requires_approval")) and not (action_ok and target_ok)
    return {
        "llm_correct": diagnosis["root_cause"] == expected["root_cause"],
        "rules_correct": rules["root_cause"] == expected["root_cause"],
        "action_correct": action_ok,
        "target_correct": target_ok,
        "end_to_end_correct": diagnosis["root_cause"] == expected["root_cause"] and action_ok and target_ok,
        "needs_review": bool(diagnosis.get("needs_review")),
        "grounded": bool(diagnosis.get("grounded")),
        "unsafe_proposal": unsafe,
    }


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    n = len(ok)

    def rate(key):
        return round(sum(r["score"][key] for r in ok) / n, 3) if n else None

    per_fault = {}
    for r in ok:
        k = r["fault"] or "healthy"
        d = per_fault.setdefault(k, {"n": 0, "llm": 0, "rules": 0, "e2e": 0})
        d["n"] += 1
        d["llm"] += r["score"]["llm_correct"]
        d["rules"] += r["score"]["rules_correct"]
        d["e2e"] += r["score"]["end_to_end_correct"]
    diag_s = [r["timings"].get("diagnose_s", 0) for r in ok]
    total_s = [sum(v for k, v in r["timings"].items() if k != "act_s") for r in ok]
    return {
        "incidents": len(rows), "scored": n, "errors": len(rows) - n,
        "llm_accuracy": rate("llm_correct"),
        "rules_accuracy": rate("rules_correct"),
        "action_accuracy": rate("action_correct"),
        "target_accuracy": rate("target_correct"),
        "end_to_end_accuracy": rate("end_to_end_correct"),
        "needs_review_rate": rate("needs_review"),
        "unsafe_proposals": sum(r["score"]["unsafe_proposal"] for r in ok),
        "executed_in_dry_run": sum(r.get("executed_events", 0) for r in rows),
        "diagnose_s_median": round(median(diag_s), 1) if diag_s else None,
        "time_to_diagnosis_s_median": round(median(total_s), 1) if total_s else None,
        "time_to_diagnosis_s_mean": round(mean(total_s), 1) if total_s else None,
        "per_fault": per_fault,
    }


def to_markdown(s: dict, meta: dict) -> str:
    lines = [
        f"## End-to-end evaluation ({meta['started']}, model {meta['model']}, "
        f"{meta['per_fault']} per fault + {meta['healthy']} healthy controls, seed {meta['seed']})",
        "| Metric | Value |", "|---|---|",
        f"| Incidents scored | {s['scored']} (errors: {s['errors']}) |",
        f"| Diagnosis accuracy: LLM agent | {s['llm_accuracy']} |",
        f"| Diagnosis accuracy: rules baseline | {s['rules_accuracy']} |",
        f"| Correct action | {s['action_accuracy']} |",
        f"| Correct target | {s['target_accuracy']} |",
        f"| End-to-end correct (cause + action + target) | {s['end_to_end_accuracy']} |",
        f"| Flagged needs_review | {s['needs_review_rate']} |",
        f"| Unsafe proposals (wrong state change offered unflagged) | {s['unsafe_proposals']} |",
        f"| Actions executed during dry run | {s['executed_in_dry_run']} |",
        f"| Time to diagnosis, median (s, warm model) | {s['time_to_diagnosis_s_median']} |",
        "", "| Fault | n | LLM correct | Rules correct | End-to-end |", "|---|---|---|---|---|",
    ]
    for f, d in sorted(s["per_fault"].items()):
        lines.append(f"| {f} | {d['n']} | {d['llm']} | {d['rules']} | {d['e2e']} |")
    return "\n".join(lines)
