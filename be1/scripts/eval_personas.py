"""Persona eval: giả lập nhiều kiểu khách hàng (non-tech, high-tech, teen, trẻ em, người già,
khách giận, mặc cả, gõ không dấu...) chat multi-turn với agent, in transcript đầy đủ.

Output:
  - stdout: transcript từng lượt (khách nói gì / agent trả lời gì / turn_type / latency)
  - logs/eval_transcript_<tag>.md  : transcript kèm rubric — đưa cho LLM ngoài hoặc Claude Code chấm
  - logs/eval_personas_<tag>.json  : report máy đọc được (routing pass/fail từng turn)

Chạy:  python scripts/eval_personas.py                     # cần server đang chạy ở --base
       python scripts/eval_personas.py --include-core      # chạy kèm bộ eval/scenarios.jsonl có sẵn
       python scripts/eval_personas.py --only p05,p08      # chỉ chạy vài kịch bản (prefix match)
       python scripts/eval_personas.py --judge             # chấm hallucination bằng judge (JUDGE_API_KEY)

Kỳ vọng turn_type viết LỎNG (routing đúng nhánh); CHẤT LƯỢNG câu trả lời chấm bằng file
transcript markdown (LLM judge / Claude Code) — mỗi turn có ghi chú 'check' mô tả hành vi đúng.
"""
import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import ROOT, TURN_LOG  # noqa: E402
from eval_run import authenticate, create_chat_session, run_turn  # noqa: E402

RUBRIC = """\
## Hướng dẫn chấm (dành cho LLM judge / Claude Code)

Bạn là giám khảo chấm chất lượng chatbot tư vấn siêu thị điện máy. Với TỪNG lượt trả lời
của agent bên dưới, chấm theo các tiêu chí:

1. **Hiểu đúng ý khách** (kể cả không dấu, viết tắt, teen-speak, mô tả bằng công dụng).
2. **Grounded**: mọi con số/thông số/khuyến mãi phải có trong dữ liệu; không bịa. Thiếu
   thông tin thì phải nói "chưa có thông tin" (null-honesty).
3. **Đúng vai saler lễ phép**: xưng hô phù hợp persona (bà lớn tuổi, trẻ em, khách giận...),
   đồng cảm khi khách khiếu nại, không vòng vo khi khách đã phó thác.
4. **Giữ ngữ cảnh multi-turn**: nhớ slot đã nói, reset khi đổi loại sản phẩm, khôi phục
   khi khách quay lại chủ đề cũ, theo Ý CUỐI CÙNG khi khách đổi ý trong 1 câu.
5. **Mục 'Check' của từng turn** là hành vi kỳ vọng cụ thể — đối chiếu trực tiếp.

Với mỗi turn trả về: `PASS / WEAK / FAIL` + 1 câu lý do. Cuối cùng tổng hợp: tỷ lệ pass,
các pattern lỗi lặp lại, và đề xuất fix hệ thống (routing / prompt / data).
"""


def load_scenarios(paths: list[Path]) -> list[dict]:
    """Đọc cả JSONL (1 object/dòng) lẫn các object JSON pretty-print nối tiếp nhau."""
    decoder = json.JSONDecoder()
    scenarios = []
    for p in paths:
        text = p.read_text()
        idx = 0
        while idx < len(text):
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text):
                break
            obj, end = decoder.raw_decode(text, idx)
            scenarios.append(obj)
            idx = end
    return scenarios


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("BE1_BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--scenarios", default=str(ROOT / "eval" / "persona_scenarios.jsonl"))
    ap.add_argument("--include-core", action="store_true",
                    help="chạy kèm bộ eval/scenarios.jsonl có sẵn của luồng eval")
    ap.add_argument("--only", default="", help="lọc kịch bản theo prefix id, phân tách bằng dấu phẩy")
    ap.add_argument("--judge", action="store_true", help="chấm hallucination các turn vừa chạy")
    ap.add_argument("--phone", default=os.getenv("BE1_TEST_PHONE", "0900000002"))
    ap.add_argument("--password", default=os.getenv("BE1_TEST_PASSWORD", "smoke-test-password"))
    args = ap.parse_args()

    paths = [Path(args.scenarios)]
    if args.include_core:
        paths.append(ROOT / "eval" / "scenarios.jsonl")
    scenarios = load_scenarios(paths)
    if args.only:
        prefixes = tuple(x.strip() for x in args.only.split(",") if x.strip())
        scenarios = [s for s in scenarios if s["id"].startswith(prefixes)]
    if not scenarios:
        print("Không có kịch bản nào khớp bộ lọc.", file=sys.stderr)
        sys.exit(2)

    run_tag = uuid.uuid4().hex[:6]
    results, sessions = [], []
    md: list[str] = [
        f"# Transcript đánh giá agent — run `{run_tag}` "
        f"({datetime.datetime.now():%Y-%m-%d %H:%M})\n",
        RUBRIC,
        "\n---\n",
    ]

    with httpx.Client(timeout=90) as client:
        authenticate(client, args.base, phone=args.phone, password=args.password)
        for sc in scenarios:
            persona = sc.get("persona", "(không ghi persona)")
            print(f"\n{'=' * 70}\n[{sc['id']}] {persona}\n  mục tiêu: {sc['desc']}\n{'=' * 70}")
            md.append(f"\n## {sc['id']}\n\n- **Persona:** {persona}\n- **Mục tiêu test:** {sc['desc']}\n")
            session_id = create_chat_session(client, args.base, title=f"Persona {run_tag}: {sc['id']}")
            sessions.append(session_id)
            sc_pass, turn_logs = True, []
            for i, t in enumerate(sc["turns"], 1):
                try:
                    out = run_turn(client, args.base, session_id, t["user"])
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 401:
                        raise
                    # access token 15 phút hết hạn giữa run dài -> login lại và thử lại 1 lần
                    authenticate(client, args.base, phone=args.phone, password=args.password)
                    out = run_turn(client, args.base, session_id, t["user"])
                ok = out["turn_type"] in t["expect_turn_type"]
                sc_pass &= ok
                turn_logs.append({**out, "user": t["user"], "expected": t["expect_turn_type"],
                                  "check": t.get("check"), "ok": ok})
                mark = "ok  " if ok else "FAIL"
                print(f"\n  KHÁCH : {t['user']}")
                print(f"  AGENT : [{out['turn_type']}] {out['text']}")
                print(f"  [{mark}] routing expect={t['expect_turn_type']} "
                      f"first_chunk={out['first_chunk_ms']}ms total={out['total_ms']}ms")
                md.append(f"\n### Turn {i}\n\n"
                          f"**Khách:** {t['user']}\n\n"
                          f"**Agent** (`{out['turn_type']}`, {out['total_ms']}ms):\n\n"
                          f"> {(out['text'] or '(không có text)').replace(chr(10), chr(10) + '> ')}\n")
                if t.get("check"):
                    md.append(f"\n**Check:** {t['check']}\n")
                if not ok:
                    md.append(f"\n**⚠ ROUTING FAIL:** got `{out['turn_type']}`, "
                              f"expected one of `{t['expect_turn_type']}`\n")
            results.append({"id": sc["id"], "persona": persona, "desc": sc["desc"],
                            "pass": sc_pass, "session_id": session_id, "turns": turn_logs})

    n_pass = sum(r["pass"] for r in results)
    n_turns = sum(len(r["turns"]) for r in results)
    n_turn_ok = sum(t["ok"] for r in results for t in r["turns"])
    summary = (f"scenarios: {n_pass}/{len(results)} pass | "
               f"turns routing: {n_turn_ok}/{n_turns} ok")

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    md.append(f"\n---\n\n## Kết quả routing tự động\n\n{summary}\n")
    for r in results:
        if not r["pass"]:
            bad = [f"t{i + 1}" for i, t in enumerate(r["turns"]) if not t["ok"]]
            md.append(f"- FAIL `{r['id']}` ({', '.join(bad)}): {r['desc']}\n")
    md_path = logs_dir / f"eval_transcript_{run_tag}.md"
    md_path.write_text("".join(md))
    report_path = logs_dir / f"eval_personas_{run_tag}.json"
    report_path.write_text(json.dumps(
        {"run_tag": run_tag, "summary": summary, "results": results},
        ensure_ascii=False, indent=2))

    print(f"\n{'=' * 70}\n=== {summary} ===")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['id']} — {r['persona']}")
    print(f"\ntranscript (đưa cho LLM/Claude chấm): {md_path}")
    print(f"report JSON: {report_path}")

    if args.judge:
        import asyncio

        from app.judge import aggregate, judge_turn  # noqa: E402

        records = [json.loads(l) for l in TURN_LOG.read_text().splitlines() if l]
        records = [r for r in records if r["session_id"] in set(sessions)]
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
        jout = logs_dir / f"eval_judgments_personas_{run_tag}.jsonl"
        with jout.open("w") as f:
            for j in judged:
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
        print(f"judgments: {jout}")


if __name__ == "__main__":
    main()
