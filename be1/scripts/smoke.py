"""Smoke test end-to-end qua HTTP thật (SSE). Chạy: python scripts/smoke.py

Yêu cầu server đang chạy: MOCK_LLM=1 uvicorn app.main:app --port 8100
"""
import json
import os
import sys

import httpx

BASE = os.getenv("BE1_BASE_URL", "http://127.0.0.1:8100").rstrip("/")
PHONE = os.getenv("BE1_TEST_PHONE", "0900000001")
PASSWORD = os.getenv("BE1_TEST_PASSWORD", "smoke-test-password")
CLIENT = httpx.Client(timeout=30)


def authenticate() -> None:
    login = CLIENT.post(
        f"{BASE}/auth/login",
        json={"phone": PHONE, "password": PASSWORD},
    )
    if login.status_code == 200:
        return
    registered = CLIENT.post(
        f"{BASE}/auth/register",
        json={
            "phone": PHONE,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    if registered.status_code != 201:
        raise RuntimeError(
            "Cannot authenticate the smoke user. Set BE1_TEST_PHONE and "
            f"BE1_TEST_PASSWORD. Login={login.text}; register={registered.text}"
        )


def create_session() -> str:
    response = CLIENT.post(
        f"{BASE}/chat/sessions",
        json={"title": "Smoke test"},
    )
    response.raise_for_status()
    return response.json()["id"]


def turn(session_id: str, message: str) -> list[dict]:
    events = []
    with CLIENT.stream(
        "POST",
        f"{BASE}/chat/sessions/{session_id}/messages",
        json={"message": message},
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    text = "".join(e.get("content", "") for e in events if e["type"] == "text_chunk")
    done = next(e["turn_type"] for e in events if e["type"] == "done")
    funnel = next((e for e in events if e["type"] == "funnel_count"), None)
    print(f"\n>>> {message}")
    if funnel:
        print(f"    [funnel {funnel['count']}/{funnel['total']} | filters={funnel['filters']}]")
    print(f"    [{done}] {text[:200]}")
    return events


def expect(cond: bool, label: str) -> None:
    print(("    PASS  " if cond else "    FAIL  ") + label)
    if not cond:
        sys.exit(1)


authenticate()
SESSION = create_session()

e1 = turn(SESSION, "chào em, anh muốn mua máy lạnh cho phòng ngủ")
expect(any(x["type"] == "question" for x in e1), "turn1: bot hỏi ngược khi thiếu thông tin")

e2 = turn(SESSION, "tầm 12 triệu thôi, phòng anh 15m2, ưu tiên êm với tiết kiệm điện")
done2 = next(x["turn_type"] for x in e2 if x["type"] == "done")
expect(done2 in ("ask", "compare"), "turn2: nhận slot budget+area, tiếp tục flow")

e3 = turn(SESSION, "thôi em tư vấn luôn đi")
expect(any(x["type"] == "product_cards" for x in e3)
       or next(x["turn_type"] for x in e3 if x["type"] == "done") == "no_match",
       "turn3: force_answer -> ra so sánh top 3 (hoặc no_match trung thực)")

e4 = turn(SESSION, "đà nẵng hôm nay có mưa không nhỉ")
expect(next(x["turn_type"] for x in e4 if x["type"] == "done") == "off_topic",
       "turn4: off-topic được kéo về lịch sự")

print("\nALL PASS — kiểm tra logs/turns.jsonl để xem turn log cho judge.")
deleted = CLIENT.delete(f"{BASE}/chat/sessions/{SESSION}")
deleted.raise_for_status()
CLIENT.close()
