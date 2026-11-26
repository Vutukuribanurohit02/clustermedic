from clustermedic.agent import llm
from clustermedic.evaluation.compare import to_markdown


def test_model_switch_is_read_at_call_time(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": '{"ok": "ok"}'}}

    monkeypatch.setattr(llm.requests, "post", lambda url, timeout, json: seen.update(json) or R())
    llm.set_model("llama3.1:8b")
    try:
        llm.chat_json("s", "u", {"type": "object"})
        assert seen["model"] == "llama3.1:8b" and seen["keep_alive"]
    finally:
        llm.set_model("qwen2.5:7b")


def test_compare_table():
    by_kind = {"literal": {"n": 9, "llm": 9, "rules": 9}, "paraphrased": {"n": 9, "llm": 7, "rules": 0},
               "benign": {"n": 4, "llm": 4, "rules": 4}}
    res = {"m1": {"size_gb": 4.7, "cold_load_s": 3.0, "e2e": None,
                  "tickets": {"by_kind": by_kind, "n": 22, "seconds": [1.0, 2.0, 3.0]},
                  "injection": {"changed": 2, "unsafe": 0, "n": 8}}}
    md = to_markdown(res)
    assert "| m1 | 4.7 | 20 | 7 | 4 | 2 | 0 | 2.0 |" in md
