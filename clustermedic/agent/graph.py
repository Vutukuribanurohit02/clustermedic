"""The triage workflow as a LangGraph state machine with a human-approval pause.

intake -> gather -> retrieve -> diagnose -> propose -> [approve (pauses for a human)] -> act -> summarize
"""
import time
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import actions, diagnose, evidence
from .guardrails import injection_signals, mask_secrets
from .actions import REPO

INCIDENTS = REPO / "data/incidents"


class State(TypedDict, total=False):
    ticket: str
    dry_run: bool
    issue: int          # GitHub issue number the ticket came from (optional)
    github: bool        # open/update a GitHub issue for this incident
    injection: list[str]
    ticket_url: str
    anomalies: list[str]
    chunks: list[dict]
    diagnosis: dict
    rules: dict
    proposal: dict
    approved: bool
    result: dict
    summary: str
    timings: dict


def _timed(state: State, key: str, t0: float) -> dict:
    return {**state.get("timings", {}), key: round(time.time() - t0, 1)}


def intake_node(state: State) -> dict:
    """Load the ticket (optionally from a GitHub issue), mask secrets, flag injection attempts."""
    ticket, url = state.get("ticket", ""), ""
    if state.get("issue"):
        from clustermedic import tickets
        data = tickets.read_issue(state["issue"])
        ticket, url = f"{data['title']}\n{data['body']}", data["url"]
    ticket = mask_secrets(ticket)
    signals = injection_signals(ticket)
    if signals:
        actions.audit("injection_suspected", patterns=signals, issue=state.get("issue"))
    return {"ticket": ticket, "injection": signals, "ticket_url": url}


def gather_node(state: State) -> dict:
    t0 = time.time()
    found = evidence.anomalies(evidence.gather())
    return {"anomalies": found, "timings": _timed(state, "gather_s", t0)}


def retrieve_node(state: State, retriever=None) -> dict:
    t0 = time.time()
    query = (state.get("ticket", "") + "\n" + "\n".join(state["anomalies"])).strip()
    if retriever is None:
        from clustermedic.rag.__main__ import _retriever
        retriever = _retriever("hybrid")
    chunks = retriever.search(query, k=4) if query else []
    return {"chunks": chunks, "timings": _timed(state, "retrieve_s", t0)}


def diagnose_node(state: State) -> dict:
    d = diagnose.diagnose_llm(state.get("ticket", ""), state["anomalies"], state["chunks"])
    return {"diagnosis": d, "rules": diagnose.diagnose_rules(state["anomalies"], state.get("ticket", "")),
            "timings": {**state.get("timings", {}), "diagnose_s": d["seconds"]}}


def propose_node(state: State) -> dict:
    p = actions.propose(state["diagnosis"], state["anomalies"])
    actions.audit("proposed", **p, root_cause=state["diagnosis"]["root_cause"])
    return {"proposal": p}


def route_after_propose(state: State) -> str:
    if state.get("dry_run") or not state["proposal"]["requires_approval"]:
        return "summarize"
    return "approve"


def approve_node(state: State) -> dict:
    # Pauses the graph. The caller shows this payload to a human and resumes with True/False.
    decision = interrupt({"diagnosis": state["diagnosis"], "proposal": state["proposal"],
                          "injection": state.get("injection", [])})
    approved = decision is True
    actions.audit("approved" if approved else "denied", **state["proposal"])
    return {"approved": approved}


def route_after_approve(state: State) -> str:
    return "act" if state.get("approved") else "summarize"


def act_node(state: State) -> dict:
    t0 = time.time()
    try:
        result = actions.execute(state["proposal"])
    except Exception as e:
        result = {"applied": False, "verified": False, "error": str(e)}
    actions.audit("executed", **state["proposal"], **result)
    return {"result": result, "timings": _timed(state, "act_s", t0)}


def summarize_node(state: State) -> dict:
    d, p = state["diagnosis"], state["proposal"]
    if state.get("dry_run"):
        outcome = "dry run: no action taken"
    elif not p["requires_approval"]:
        outcome = "no automated change"
    elif not state.get("approved"):
        outcome = "fix DENIED by human; nothing changed"
    else:
        r = state.get("result", {})
        outcome = ("fix applied and verified" if r.get("verified") else
                   f"fix applied but NOT verified ({r.get('error', 'timed out')})")
    lines = [
        f"# Incident handover ({datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC})",
        f"**Ticket:** {state.get('ticket') or '(automated alert)'}",
        *([f"**Warning:** ticket contained instruction-like text ({len(state['injection'])} "
           f"pattern(s)); diagnosis is based on monitoring evidence only."]
          if state.get("injection") else []),
        "**Anomalies:**", *[f"- {a}" for a in state["anomalies"] or ["(none)"]],
        f"**Diagnosis:** {d['root_cause']} on {p['target'] or '-'} "
        f"(confidence {d['confidence']}, grounded {d['grounded']}, runbook {d['runbook']})",
        f"**Reasoning:** {d['reasoning']}",
        f"**Rules baseline said:** {state['rules']['root_cause']}",
        f"**Proposed action:** {p['action']}: {p['description']}",
        f"**Outcome:** {outcome}",
        f"**Timings (s):** {state.get('timings', {})}",
    ]
    summary = mask_secrets("\n".join(lines))
    INCIDENTS.mkdir(parents=True, exist_ok=True)
    (INCIDENTS / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md").write_text(summary + "\n")
    out = {"summary": summary}
    if not state.get("dry_run") and (state.get("issue") or state.get("github")):
        out.update(_post_ticket(state, summary, outcome))
    return out


def _post_ticket(state: State, summary: str, outcome: str) -> dict:
    """Comment on the source issue, or open a new one; close it if the fix was verified."""
    from clustermedic import tickets
    try:
        number = state.get("issue")
        if number:
            tickets.comment(number, summary)
            url = state.get("ticket_url", "")
        else:
            d = state["diagnosis"]
            opened = tickets.open_issue(
                f"[ClusterMedic] {d['root_cause']} on {state['proposal']['target'] or 'cluster'}",
                summary)
            number, url = opened["number"], opened["url"]
        if outcome == "fix applied and verified":
            tickets.close(number)
        actions.audit("ticket_updated", issue=number, closed=outcome == "fix applied and verified")
        return {"ticket_url": url}
    except Exception as e:  # ticketing must never break incident handling
        actions.audit("ticket_error", error=str(e))
        return {"ticket_url": f"(ticket update failed: {e})"}


def build_graph(retriever=None):
    g = StateGraph(State)
    g.add_node("intake", intake_node)
    g.add_node("gather", gather_node)
    g.add_node("retrieve", lambda s: retrieve_node(s, retriever))
    g.add_node("diagnose", diagnose_node)
    g.add_node("propose", propose_node)
    g.add_node("approve", approve_node)
    g.add_node("act", act_node)
    g.add_node("summarize", summarize_node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "gather")
    g.add_edge("gather", "retrieve")
    g.add_edge("retrieve", "diagnose")
    g.add_edge("diagnose", "propose")
    g.add_conditional_edges("propose", route_after_propose, ["approve", "summarize"])
    g.add_conditional_edges("approve", route_after_approve, ["act", "summarize"])
    g.add_edge("act", "summarize")
    g.add_edge("summarize", END)
    return g.compile(checkpointer=MemorySaver())


def pending_approval(graph, config) -> dict | None:
    """If the graph is paused at the approval step, return what the human must decide on."""
    snap = graph.get_state(config)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None
