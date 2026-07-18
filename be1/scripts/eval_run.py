"""Eval harness: chạy batch scenario qua authenticated chat API, check kỳ vọng, rồi (tùy chọn)
đưa chính các turn vừa sinh cho judge chấm hallucination.

Chạy:  python scripts/eval_run.py                # cần server đang chạy ở --base
       python scripts/eval_run.py --judge        # + chấm hallucination ngay sau đó
       python scripts/eval_run.py --scenarios eval/scenarios.jsonl --base http://127.0.0.1:8100

Kỳ vọng viết LỎNG (list turn_type chấp nhận được) để chạy được cả MOCK_LLM lẫn LLM thật;
chất lượng nội dung do judge chấm, không assert cứng vào text.
"""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ROOT, TURN_LOG  # noqa: E402


def authenticate(
    client: httpx.Client,
    base: str,
    *,
    phone: str,
    password: str,
) -> None:
    login = client.post(
        f"{base}/auth/login",
        json={"phone": phone, "password": password},
    )
    if login.status_code == 200:
        return
    registered = client.post(
        f"{base}/auth/register",
        json={
            "phone": phone,
            "password": password,
            "password_confirmation": password,
        },
    )
    if registered.status_code != 201:
        raise RuntimeError(
            "Cannot authenticate the eval user. Set --phone/--password. "
            f"Login={login.text}; register={registered.text}"
        )


def create_chat_session(
    client: httpx.Client,
    base: str,
    *,
    title: str,
) -> str:
    response = client.post(
        f"{base}/chat/sessions",
        json={"title": title},
    )
    response.raise_for_status()
    return response.json()["id"]


def run_turn(client: httpx.Client, base: str, session_id: str, message: str) -> dict:
    events = []
    t0 = time.perf_counter()
    first_chunk_ms = None
    with client.stream(
        "POST",
        f"{base}/chat/sessions/{session_id}/messages",
        json={"message": message},
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "text_chunk" and first_chunk_ms is None:
                    first_chunk_ms = round((time.perf_counter() - t0) * 1000)
                events.append(ev)
    return {
        "turn_type": next((e["turn_type"] for e in events if e["type"] == "done"), None),
        "text": "".join(e.get("content", "") for e in events if e["type"] == "text_chunk"),
        "first_chunk_ms": first_chunk_ms,
        "total_ms": round((time.perf_counter() - t0) * 1000),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default=os.getenv("BE1_BASE_URL", "http://127.0.0.1:8100"),
    )
    ap.add_argument("--scenarios", default=str(ROOT / "eval" / "scenarios.jsonl"))
    ap.add_argument("--judge", action="store_true", help="chấm hallucination các turn vừa chạy")
    ap.add_argument(
        "--phone",
        default=os.getenv("BE1_TEST_PHONE", "0900000002"),
        help="phone-number account used by the authenticated eval client",
    )
    ap.add_argument(
        "--password",
        default=os.getenv("BE1_TEST_PASSWORD", "smoke-test-password"),
        help="password for the authenticated eval client",
    )
    args = ap.parse_args()

    scenarios = [json.loads(l) for l in Path(args.scenarios).read_text().splitlines() if l]
    run_tag = uuid.uuid4().hex[:6]
    results, sessions = [], []

    with httpx.Client(timeout=60) as client:
        authenticate(
            client,
            args.base,
            phone=args.phone,
            password=args.password,
        )
        for sc in scenarios:
            session_id = create_chat_session(
                client,
                args.base,
                title=f"Eval {run_tag}: {sc['id']}",
            )
            sessions.append(session_id)
            sc_pass, turn_logs = True, []
            for i, t in enumerate(sc["turns"], 1):
                out = run_turn(client, args.base, session_id, t["user"])
                ok = out["turn_type"] in t["expect_turn_type"]
                sc_pass &= ok
                turn_logs.append({**out, "user": t["user"], "expected": t["expect_turn_type"], "ok": ok})
                mark = "ok " if ok else "FAIL"
                print(f"  [{mark}] {sc['id']} t{i}: got={out['turn_type']} "
                      f"expect={t['expect_turn_type']} first_chunk={out['first_chunk_ms']}ms")
            results.append({"id": sc["id"], "desc": sc["desc"], "pass": sc_pass, "turns": turn_logs})

    n_pass = sum(r["pass"] for r in results)
    chunks = [t["first_chunk_ms"] for r in results for t in r["turns"] if t["first_chunk_ms"]]
    report = {
        "run_tag": run_tag,
        "scenarios_pass": f"{n_pass}/{len(results)}",
        "latency_first_chunk_ms": {"max": max(chunks), "avg": round(sum(chunks) / len(chunks))} if chunks else None,
        "results": results,
    }
    out = ROOT / "logs" / f"eval_report_{run_tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\n=== SCENARIO: {n_pass}/{len(results)} pass ===")
    for r in results:
        if not r["pass"]:
            print(f"  FAIL {r['id']}: {r['desc']}")
    if chunks:
        print(f"latency first-chunk: avg {report['latency_first_chunk_ms']['avg']}ms, "
              f"max {report['latency_first_chunk_ms']['max']}ms (target <1500ms với LLM thật)")
    print(f"report: {out}")

    if args.judge:
        from app.judge import aggregate, judge_turn  # noqa: E402

        # server ghi turn log cùng repo -> lấy đúng các session của run này
        records = [json.loads(l) for l in TURN_LOG.read_text().splitlines() if l]
        records = [r for r in records
                   if r["session_id"] in set(sessions)
                   and r["turn_type"] in ("compare", "ask", "no_match")]
        print(f"\n=== JUDGE: chấm {len(records)} turn của run này ===")

        async def judge_all():
            sem = asyncio.Semaphore(4)

            async def one(r):
                async with sem:
                    try:
                        return {**r, "judgment": (await judge_turn(r)).model_dump()}
                    except Exception as e:
                        print(f"  ! lỗi judge: {e}", file=sys.stderr)
                        return None

            return [x for x in await asyncio.gather(*(one(r) for r in records)) if x]

        judged = asyncio.run(judge_all())
        print(json.dumps(aggregate(judged), ensure_ascii=False, indent=2))
        jout = ROOT / "logs" / f"eval_judgments_{run_tag}.jsonl"
        with jout.open("w") as f:
            for j in judged:
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
        print(f"judgments: {jout}")

    if n_pass < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
