"""Minimal Ollama chat client with JSON-schema constrained output (no LangChain needed)."""
import json
import os

import requests

OLLAMA_URL = os.getenv("CLUSTERMEDIC_OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("CLUSTERMEDIC_CHAT_MODEL", "qwen2.5:7b")


def chat_json(system: str, user: str, schema: dict, model: str = CHAT_MODEL,
              timeout_s: int = 180) -> dict:
    """Ask the model for a JSON object that matches `schema` (Ollama structured outputs)."""
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=timeout_s, json={
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    })
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])
