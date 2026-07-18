"""Judge hallucination: model ngoài (mạnh hơn) chấm từng turn theo CLAIM.

Input là turn record từ logs/turns.jsonl — quan trọng: đối chiếu với context_json
(đúng data mà LLM saler nhìn thấy), KHÔNG phải API thô.

MOCK_JUDGE=1: kiểm tra số học thuần (mọi con số trong response phải xuất hiện
trong context) — chạy được offline, không thay thế judge thật.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from .config import JUDGE_API_KEY, JUDGE_BASE_URL, JUDGE_MODEL, MOCK_JUDGE

Verdict = Literal["SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "SALER_TALK"]


class ClaimVerdict(BaseModel):
    claim: str = Field(description="Câu khẳng định (trích/diễn giải ngắn từ response)")
    verdict: Verdict
    evidence: str | None = Field(
        default=None, description="Field/giá trị trong context chứng minh, hoặc lý do không tìm thấy"
    )


class TurnJudgment(BaseModel):
    claims: list[ClaimVerdict]
    null_honesty: Literal["honest", "violated", "not_applicable"] = Field(
        description="Khi context có field null liên quan: bot thừa nhận thiếu (honest) "
                    "hay bịa ra (violated); không có field null liên quan -> not_applicable"
    )
    comment: str = Field(description="1-2 câu nhận xét tổng quan")


JUDGE_SYSTEM = """Bạn là giám khảo KHẮT KHE chấm hallucination cho chatbot tư vấn điện máy.

Bạn nhận: câu hỏi của khách, câu trả lời của bot, và CONTEXT — đúng phần dữ liệu JSON \
mà bot được phép dùng (có thể null nếu turn đó không truy xuất sản phẩm).

Nhiệm vụ: tách MỌI câu khẳng định (claim) trong câu trả lời và phán quyết từng claim:
- SUPPORTED: có dữ liệu trong CONTEXT chứng minh trực tiếp (số khớp chính xác, kể cả \
đơn vị quy đổi: 8500000 = "8.500.000đ" = "8,5 triệu").
- CONTRADICTED: mâu thuẫn với CONTEXT (sai giá, sai thông số, sai số lượng).
- UNSUPPORTED: nghe như sự thật (giá, thông số, tồn kho, khuyến mãi, xuất xứ, so sánh \
"tiết kiệm hơn X%") nhưng KHÔNG có trong CONTEXT. CONTEXT null mà bot vẫn nêu số liệu \
sản phẩm cụ thể -> UNSUPPORTED.
- SALER_TALK: xã giao, mời chào, ý kiến chủ quan không kiểm chứng được ("mẫu này đáng \
tiền", "anh chị yên tâm") — KHÔNG tính là hallucination.

Diễn giải đời thường của thông số CÓ trong context vẫn là SUPPORTED (vd context có \
noise_db_min=27.5 và bot nói "êm như thì thầm, 27.5dB").

null_honesty: nếu CONTEXT có field null mà lẽ ra cần cho câu trả lời (vd khách hỏi độ ồn \
nhưng noise_db_min=null): bot nói rõ "chưa có thông tin" -> honest; bot bịa giá trị -> \
violated; không rơi vào tình huống đó -> not_applicable.

Chấm bằng tiếng Việt. Nghiêm khắc: nghi ngờ thì KHÔNG cho SUPPORTED."""


def _get_judge_llm():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=JUDGE_MODEL, base_url=JUDGE_BASE_URL, api_key=JUDGE_API_KEY,
        temperature=0.0, timeout=60,
    )


# ---------------- mock: number cross-check thuần code ----------------

_NUM_RE = re.compile(r"\d[\d.,]*")


def _extract_numbers(text: str) -> set[float]:
    out = set()
    for raw in _NUM_RE.findall(text):
        clean = raw.strip(".,")
        # "8.500.000" -> 8500000 ; "27.5"/"27,5" -> 27.5
        if clean.count(".") > 1 or (clean.count(".") == 1 and len(clean.split(".")[-1]) == 3):
            clean = clean.replace(".", "")
        clean = clean.replace(",", ".")
        try:
            v = float(clean)
        except ValueError:
            continue
        out.add(v)
        if v < 1000:  # "8,5 triệu" / "12 tr"
            out.add(v * 1_000_000)
    return out


def _mock_judge(record: dict) -> TurnJudgment:
    context = {"context": record.get("context_json"), "funnel": record.get("funnel")}
    allowed = _extract_numbers(json.dumps(context, ensure_ascii=False))
    claims = []
    for n in sorted(_extract_numbers(record.get("response", ""))):
        ok = n in allowed or n * 1_000_000 in allowed
        claims.append(ClaimVerdict(
            claim=f"con số {n:g} trong câu trả lời",
            verdict="SUPPORTED" if ok else "UNSUPPORTED",
            evidence="khớp số trong context" if ok else "không tìm thấy trong context",
        ))
    if not claims:
        claims.append(ClaimVerdict(claim="(không có con số nào)", verdict="SALER_TALK"))
    return TurnJudgment(
        claims=claims, null_honesty="not_applicable",
        comment="MOCK: chỉ đối chiếu con số, không hiểu ngữ nghĩa — dùng judge thật để chấm điểm.",
    )


# ---------------- public API ----------------

async def judge_turn(record: dict) -> TurnJudgment:
    """record = 1 dòng của logs/turns.jsonl."""
    if MOCK_JUDGE:
        return _mock_judge(record)
    llm = _get_judge_llm().with_structured_output(TurnJudgment)
    user_msg = (
        f"KHÁCH HỎI: {record['query']}\n\n"
        f"BOT TRẢ LỜI:\n{record['response']}\n\n"
        f"CONTEXT (nguồn duy nhất bot được dùng):\n"
        f"{json.dumps(record.get('context_json'), ensure_ascii=False)}\n\n"
        f"FUNNEL (số sản phẩm khớp bộ lọc): {json.dumps(record.get('funnel'), ensure_ascii=False)}"
    )
    return await llm.ainvoke([("system", JUDGE_SYSTEM), ("user", user_msg)])


def aggregate(judged: list[dict]) -> dict:
    """judged = list {**turn_record, 'judgment': TurnJudgment.model_dump()}. Trả metrics tổng."""
    n_turns = len(judged)
    counts = {"SUPPORTED": 0, "CONTRADICTED": 0, "UNSUPPORTED": 0, "SALER_TALK": 0}
    bad_turns = 0
    honest = violated = 0
    for j in judged:
        verdicts = [c["verdict"] for c in j["judgment"]["claims"]]
        for v in verdicts:
            counts[v] += 1
        if any(v in ("CONTRADICTED", "UNSUPPORTED") for v in verdicts):
            bad_turns += 1
        nh = j["judgment"]["null_honesty"]
        honest += nh == "honest"
        violated += nh == "violated"
    factual = counts["SUPPORTED"] + counts["CONTRADICTED"] + counts["UNSUPPORTED"]
    return {
        "turns_judged": n_turns,
        "claims": counts,
        "hallucination_rate_turn": round(bad_turns / n_turns, 3) if n_turns else None,
        "grounded_rate_claim": round(counts["SUPPORTED"] / factual, 3) if factual else None,
        "null_honesty_rate": round(honest / (honest + violated), 3) if (honest + violated) else None,
    }
