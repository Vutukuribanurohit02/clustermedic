"""Minimal Ollama chat client with JSON-schema constrained output (no LangChain needed).

The model is read at CALL time from `llm.CHAT_MODEL`, so evaluations can switch models
(set_model) without restarting. keep_alive keeps the model in GPU memory between incidents,
so alert-driven runs don't pay a cold-start reload after 5 idle minutes.
"""
import json
import os

import requests

OLLAMA_URL = os.getenv("CLUSTERMEDIC_OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("CLUSTERMEDIC_CHAT_MODEL", "qwen2.5:7b")
KEEP_ALIVE = os.getenv("CLUSTERMEDIC_KEEP_ALIVE", "30m")


def set_model(name: str) -> None:
    global CHAT_MODEL
    CHAT_MODEL = name


def current_model() -> str:
    return CHAT_MODEL


def chat_json(system: str, user: str, schema: dict, model: str | None = None,
              timeout_s: int = 180) -> dict:
    """Ask the model for a JSON object that matches `schema` (Ollama structured outputs)."""
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=timeout_s, json={
        "model": model or CHAT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": 8192},
    })
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])
