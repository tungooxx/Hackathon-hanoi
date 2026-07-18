"""Chấm hallucination batch trên logs/turns.jsonl bằng judge (model ngoài mạnh hơn).

Chạy:  python scripts/judge_batch.py                 # chấm mọi turn có response + đáng chấm
       python scripts/judge_batch.py --sessions a b  # chỉ chấm các session này
       MOCK_JUDGE=1 python scripts/judge_batch.py    # offline number cross-check

Output: logs/judgments.jsonl + bảng metrics. Có Langfuse key -> push scores lên luôn.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import JUDGMENT_LOG, LANGFUSE_ENABLED, MOCK_JUDGE, TURN_LOG  # noqa: E402
from app.judge import aggregate, judge_turn  # noqa: E402

# off_topic không có claim sản phẩm; ask vẫn chấm (bot có thể bịa "em đang có N mẫu")
JUDGEABLE = {"compare", "ask", "no_match"}
CONCURRENCY = 4


async def _judge_all(records: list[dict]) -> list[dict]:
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(r: dict) -> dict | None:
        nonlocal done
        async with sem:
            try:
                j = await judge_turn(r)
            except Exception as e:  # 1 turn hỏng không giết cả batch
                print(f"  ! lỗi judge turn {r['ts']}: {e}", file=sys.stderr)
                return None
            done += 1
            print(f"  {done}/{len(records)} judged", end="\r", flush=True)
            return {**r, "judgment": j.model_dump()}

    results = await asyncio.gather(*(one(r) for r in records))
    print()
    return [r for r in results if r]


def _push_langfuse(judged: list[dict], metrics: dict) -> None:
    from langfuse import get_client

    lf = get_client()
    for j in judged:
        verdicts = [c["verdict"] for c in j["judgment"]["claims"]]
        bad = sum(v in ("CONTRADICTED", "UNSUPPORTED") for v in verdicts)
        with lf.start_as_current_span(
            name="judge_turn",
            input={"query": j["query"], "turn_type": j["turn_type"]},
            output=j["judgment"],
        ) as span:
            span.update_trace(session_id=j["session_id"], tags=["judge"])
            span.score_trace(name="hallucinated_claims", value=bad)
            span.score_trace(name="grounded", value=0 if bad else 1)
    lf.flush()
    print(f"-> đã push {len(judged)} judge traces + scores lên Langfuse")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(TURN_LOG))
    ap.add_argument("--output", default=str(JUDGMENT_LOG))
    ap.add_argument("--sessions", nargs="*", help="chỉ chấm các session_id này")
    ap.add_argument("--limit", type=int, help="chấm N turn cuối")
    args = ap.parse_args()

    records = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line]
    records = [r for r in records if r["turn_type"] in JUDGEABLE and r.get("response")]
    if args.sessions:
        records = [r for r in records if r["session_id"] in set(args.sessions)]
    if args.limit:
        records = records[-args.limit:]
    if not records:
        sys.exit("Không có turn nào để chấm (cần turn_type compare/ask/no_match).")

    mode = "MOCK (number cross-check)" if MOCK_JUDGE else "LLM judge"
    print(f"Chấm {len(records)} turn — mode: {mode}")
    judged = asyncio.run(_judge_all(records))

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    with out.open("w") as f:
        for j in judged:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    metrics = aggregate(judged)
    print(f"\n=== METRICS ({mode}) ===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    flagged = [j for j in judged if any(
        c["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for c in j["judgment"]["claims"])]
    if flagged:
        print(f"\n=== {len(flagged)} TURN BỊ GẮN CỜ ===")
        for j in flagged:
            print(f"\n[{j['turn_type']}] {j['query'][:80]}")
            for c in j["judgment"]["claims"]:
                if c["verdict"] in ("CONTRADICTED", "UNSUPPORTED"):
                    print(f"  {c['verdict']}: {c['claim']} — {c.get('evidence')}")
    else:
        print("\nKhông turn nào bị gắn cờ hallucination.")
    print(f"\nChi tiết: {out}")

    if LANGFUSE_ENABLED:
        _push_langfuse(judged, metrics)


if __name__ == "__main__":
    main()
