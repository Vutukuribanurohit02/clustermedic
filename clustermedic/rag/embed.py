"""Embeddings from a local Ollama model (default: nomic-embed-text)."""
import os

import requests

OLLAMA_URL = os.getenv("CLUSTERMEDIC_OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("CLUSTERMEDIC_EMBED_MODEL", "nomic-embed-text")

# nomic-embed-text is trained with task prefixes; using them improves retrieval.
_PREFIX = {"nomic-embed-text": ("search_document: ", "search_query: ")}


class OllamaEmbedder:
    def __init__(self, model: str = EMBED_MODEL, url: str = OLLAMA_URL):
        self.model, self.url = model, url
        self.doc_prefix, self.query_prefix = _PREFIX.get(model.split(":")[0], ("", ""))

    def _embed(self, texts: list[str]) -> list[list[float]]:
        r = requests.post(f"{self.url}/api/embed", json={"model": self.model, "input": texts}, timeout=120)
        r.raise_for_status()
        return r.json()["embeddings"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]
