"""RAG unit tests: chunking, BM25, and evaluation metrics (no Ollama needed)."""
from pathlib import Path

from clustermedic.rag.bm25 import BM25
from clustermedic.rag.chunking import chunk_dir, chunk_runbook, parse_front_matter
from clustermedic.rag.evaluate import evaluate, runbook_rank
from clustermedic.rag.store import BM25Retriever, RUNBOOKS

TEMPLATE = """---
id: RB-099
title: Test runbook
fault_type: test
components: [slurm, storage]
---

## Symptoms
- Jobs fail with No space left on device.

## Fix
-

## Verify
1.
"""


def test_front_matter_lists():
    meta, body = parse_front_matter(TEMPLATE)
    assert meta["id"] == "RB-099" and meta["components"] == ["slurm", "storage"]
    assert body.lstrip().startswith("## Symptoms")


def test_empty_template_sections_are_skipped(tmp_path):
    p = tmp_path / "RB-099-test.md"
    p.write_text(TEMPLATE)
    chunks = chunk_runbook(p)
    assert [c.section for c in chunks] == ["Symptoms"]
    assert chunks[0].id == "RB-099#symptoms" and chunks[0].meta["components"] == "slurm,storage"


def test_real_runbooks_chunk_cleanly():
    chunks = chunk_dir(RUNBOOKS)
    assert {c.runbook for c in chunks} == {f"RB-{i:03d}" for i in range(1, 11)}
    assert len({c.id for c in chunks}) == len(chunks)  # ids unique


def test_bm25_prefers_matching_doc():
    bm = BM25(["fan reading zero rpm", "gpu xid 48 ecc", "disk full no space"])
    s = bm.scores("xid 48")
    assert s.index(max(s)) == 1


def test_runbook_rank_dedupes():
    res = [{"runbook": "RB-001"}, {"runbook": "RB-001"}, {"runbook": "RB-003"}]
    assert runbook_rank(res, "RB-003") == 2 and runbook_rank(res, "RB-009") is None


def test_bm25_baseline_runs_on_question_set():
    res = evaluate(BM25Retriever())
    assert res["n"] == 20 and 0 <= res["hit@1"] <= 1


class _Fake:
    def __init__(self, order):
        self.order = order

    def search(self, query, k=5):
        return [{"id": i, "runbook": i.split("#")[0], "section": "", "score": 0, "text": ""}
                for i in self.order[:k]]


def test_hybrid_rrf_rewards_agreement_and_covers_blind_spots():
    from clustermedic.rag.store import HybridRetriever
    a = _Fake(["RB-001#x", "RB-002#x", "RB-003#x"])
    b = _Fake(["RB-003#x", "RB-002#x", "RB-009#x"])
    ids = [h["id"] for h in HybridRetriever([a, b]).search("q", k=4)]
    assert set(ids[:2]) == {"RB-002#x", "RB-003#x"}   # found by both retrievers -> top
    assert set(ids) == {"RB-001#x", "RB-002#x", "RB-003#x", "RB-009#x"}
