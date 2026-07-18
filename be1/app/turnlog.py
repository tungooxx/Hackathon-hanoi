"""Log mỗi turn ra JSONL — input cho judge/eval + deliverable 'log nguồn dữ liệu'."""
import json
import time

from .config import TURN_LOG


def log_turn(session_id: str, query: str, events: list[dict]) -> None:
    text = "".join(e["content"] for e in events if e["type"] == "text_chunk")
    record = {
        "ts": time.time(),
        "session_id": session_id,
        "query": query,
        "response": text,
        "turn_type": next((e["turn_type"] for e in events if e["type"] == "done"), None),
        "intent": next((e["data"] for e in events if e["type"] == "_intent"), None),
        "context_json": next((e for e in events if e["type"] == "_context"), None),
        "funnel": next((e for e in events if e["type"] == "funnel_count"), None),
        "timings_ms": {e["stage"]: e["ms"] for e in events if e["type"] == "_stage"},
    }
    TURN_LOG.parent.mkdir(exist_ok=True)
    # Vietnamese assistant responses must not depend on the Windows console
    # code page.  A logging failure runs during SSE generator cleanup and can
    # otherwise terminate an already-completed client stream.
    with TURN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
