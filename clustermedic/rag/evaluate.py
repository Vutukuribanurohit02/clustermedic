"""Retrieval evaluation: does the right runbook come back for each question?"""
import json
from pathlib import Path

from .store import REPO

QUESTIONS = REPO / "eval/retrieval_questions.jsonl"


def runbook_rank(results: list[dict], expected: str) -> int | None:
    """1-based rank of the expected runbook among distinct runbooks in the results."""
    seen = []
    for r in results:
        if r["runbook"] not in seen:
            seen.append(r["runbook"])
    return seen.index(expected) + 1 if expected in seen else None


def evaluate(retriever, questions: Path = QUESTIONS, k: int = 10) -> dict:
    rows = [json.loads(l) for l in questions.read_text().splitlines() if l.strip()]
    ranks, misses = [], []
    for q in rows:
        rank = runbook_rank(retriever.search(q["question"], k=k), q["expected"])
        ranks.append(rank)
        if rank != 1:
            misses.append({"question": q["question"], "expected": q["expected"], "rank": rank})
    n = len(rows)
    return {
        "n": n,
        "hit@1": sum(r == 1 for r in ranks) / n,
        "hit@3": sum(r is not None and r <= 3 for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "misses": misses,
    }
