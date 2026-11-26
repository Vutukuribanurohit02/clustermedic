"""Chroma vector store over runbook chunks, plus a BM25 retriever with the same interface."""
from pathlib import Path

from .bm25 import BM25
from .chunking import chunk_dir

REPO = Path(__file__).resolve().parents[2]
RUNBOOKS = REPO / "runbooks"
PERSIST = REPO / "data/chroma"
COLLECTION = "runbooks"


def build_index(embedder, runbooks: Path = RUNBOOKS, persist: Path = PERSIST) -> int:
    import chromadb
    chunks = chunk_dir(runbooks)
    client = chromadb.PersistentClient(path=str(persist))
    try:
        client.delete_collection(COLLECTION)   # rebuild from scratch every time
    except Exception:
        pass
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    col.add(ids=[c.id for c in chunks],
            embeddings=embedder.embed_documents([c.text for c in chunks]),
            documents=[c.text for c in chunks],
            metadatas=[c.meta for c in chunks])
    return len(chunks)


class VectorRetriever:
    def __init__(self, embedder, persist: Path = PERSIST):
        import chromadb
        self.embedder = embedder
        self.col = chromadb.PersistentClient(path=str(persist)).get_collection(COLLECTION)

    def search(self, query: str, k: int = 5) -> list[dict]:
        res = self.col.query(query_embeddings=[self.embedder.embed_query(query)], n_results=k)
        return [{"id": i, "runbook": m["runbook"], "section": m["section"],
                 "score": round(1 - d, 4), "text": doc}
                for i, m, d, doc in zip(res["ids"][0], res["metadatas"][0],
                                        res["distances"][0], res["documents"][0])]


class BM25Retriever:
    def __init__(self, runbooks: Path = RUNBOOKS):
        self.chunks = chunk_dir(runbooks)
        self.bm25 = BM25([c.text for c in self.chunks])

    def search(self, query: str, k: int = 5) -> list[dict]:
        scored = sorted(zip(self.bm25.scores(query), self.chunks), key=lambda x: -x[0])[:k]
        return [{"id": c.id, "runbook": c.runbook, "section": c.section,
                 "score": round(s, 4), "text": c.text} for s, c in scored]
