"""2 lượt LLM/turn: extract_intent (structured, model nhỏ) + stream_phrase (streaming, model lớn).

MOCK_LLM=1 -> regex/template, chạy full luồng không cần API key.
"""
import asyncio
import json
import re
from collections.abc import AsyncIterator

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_LARGE, LLM_MODEL_SMALL, MOCK_LLM
from .schemas import IntentResult

INTENT_SYSTEM = """Bạn là bộ phân tích ý định cho trợ lý bán hàng Điện Máy Xanh.
Trích xuất từ tin nhắn khách (tiếng Việt có thể sai chính tả, không dấu, viết tắt).
Ngữ cảnh hội thoại: category hiện tại = {category}, thông tin đã có = {slots}.

Quy tắc:
- intent_type: "new_topic" nếu khách chuyển sang loại sản phẩm khác; "same_topic" nếu bổ sung \
thông tin; "off_topic" nếu không liên quan mua sắm điện máy; "force_answer" nếu khách muốn \
được gợi ý/chốt ngay ("tư vấn luôn đi", "cứ gợi ý đi", "sao cũng được").
- budget_max đổi về VND: "10tr"/"10 triệu" -> 10000000. "tầm"/"khoảng" vẫn tính là budget_max.
- product_mentions: chép NGUYÊN VĂN tên/mã sản phẩm khách gõ, không sửa chính tả.
- priorities theo thứ tự khách nhắc: tiết kiệm điện->tiet_kiem_dien, êm/ít ồn->it_on, rẻ->gia_re.

Ví dụ:
"mya lanh cho fong 15m2 tam 8tr" -> category=may_lanh, area_m2=15, budget_max=8000000, intent_type=new_topic
"thoi co gi tu van luon di" -> intent_type=force_answer
"hom nay da nang mua khong" -> intent_type=off_topic"""

SALER_SYSTEM = """Bạn là nhân viên tư vấn Điện Máy Xanh — thân thiện, gọi khách là "anh/chị", xưng "em".
Quy tắc SẮT (vi phạm = sa thải):
- MỌI con số (giá, dB, sao năng lượng, m²) phải lấy đúng từ JSON được cung cấp, kèm nhắc nguồn tự nhiên.
- Field null/thiếu trong JSON -> nói thẳng "phần này bên em chưa có thông tin", KHÔNG đoán.
- Không nói "sản phẩm nào cũng tốt" — phải nêu trade-off cụ thể giữa các lựa chọn.
- Giải thích thông số bằng ngôn ngữ đời thường (38dB ≈ tiếng thì thầm; 5 sao = tiết kiệm điện nhất).
- Trả lời như đang NHẮN TIN thật với khách, KHÔNG viết thành một đoạn văn dài: chia câu trả lời
  thành 2-4 tin nhắn ngắn (mỗi tin 1-2 câu, súc tích, giọng tự nhiên như người thật đang gõ), \
mỗi tin cách nhau ĐÚNG MỘT dòng trống.
- Tổng cộng tối đa ~120 từ."""


def _get_llm(model: str, temperature: float):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model, base_url=LLM_BASE_URL, api_key=LLM_API_KEY,
        temperature=temperature, timeout=30,
    )


# ---------------- intent ----------------

_CATEGORY_KW = {
    "may_lanh": ["máy lạnh", "may lanh", "mya lanh", "điều hòa", "dieu hoa", "máy điều hòa"],
    "tu_lanh": ["tủ lạnh", "tu lanh"],
    "may_giat": ["máy giặt", "may giat"],
}


def _mock_intent(text: str, category: str | None) -> IntentResult:
    low = text.lower()
    cat = next((c for c, kws in _CATEGORY_KW.items() if any(k in low for k in kws)), None)
    slots: dict = {}
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tr\b|trieu|triệu)", low):
        slots["budget_max"] = float(m.group(1).replace(",", ".")) * 1_000_000
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|mét vuông|met vuong)", low):
        slots["area_m2"] = float(m.group(1).replace(",", "."))
    prios = []
    if re.search(r"tiết kiệm|tiet kiem|điện|dien", low):
        prios.append("tiet_kiem_dien")
    if re.search(r"ồn|on ào|êm|em ái|yên", low):
        prios.append("it_on")
    if re.search(r"\brẻ|\bre\b|giá tốt", low):
        prios.append("gia_re")
    force = bool(re.search(r"luôn đi|luon di|chốt|gợi ý (luôn|ngay)|sao cũng được|tu van luon", low))
    if force:
        itype = "force_answer"
    elif cat and cat != category:
        itype = "new_topic"
    elif cat or slots or prios:
        itype = "same_topic"
    else:
        # mock không hiểu ngữ nghĩa: không có tín hiệu nào -> off_topic
        # (LLM thật phân biệt được "phòng ngủ" là trả lời câu hỏi vs câu lạc đề)
        itype = "off_topic"
    return IntentResult(
        intent_type=itype, category=cat, priorities=prios,
        budget_max=slots.get("budget_max"), area_m2=slots.get("area_m2"),
    )


async def extract_intent(text: str, category: str | None, slots: dict) -> IntentResult:
    if MOCK_LLM:
        return _mock_intent(text, category)
    llm = _get_llm(LLM_MODEL_SMALL, 0.0).with_structured_output(IntentResult)
    system = INTENT_SYSTEM.format(category=category or "chưa có", slots=json.dumps(slots, ensure_ascii=False))
    return await llm.ainvoke([("system", system), ("user", text)])


# ---------------- phrasing (streaming) ----------------

async def _mock_stream(text: str) -> AsyncIterator[str]:
    for word in text.split(" "):
        yield word + " "
        await asyncio.sleep(0.01)


def _mock_phrase(kind: str, context: dict) -> str:
    if kind == "ask":
        slot = context["question_slot"]
        n = context["candidate_count"]
        asks = {
            "budget_max": f"Dạ để em lọc đúng trong {n} mẫu đang có, anh/chị dự định ngân sách khoảng bao nhiêu ạ?",
            "area_m2": f"Dạ em đang có {n} mẫu phù hợp. Phòng mình rộng khoảng bao nhiêu mét vuông, có bị nắng chiếu trực tiếp không ạ?",
            "brand": "Anh/chị có ưu tiên hãng nào không ạ, hay để em chọn theo hiệu năng/giá?",
        }
        return asks.get(slot, f"Anh/chị cho em xin thêm thông tin về {slot} ạ?")
    if kind == "compare":
        lines = []
        for p in context["products"]:
            price = f"{p['price_sale']:,}đ".replace(",", ".")
            noise = f", êm {p['noise_db_min']}dB" if p.get("noise_db_min") else ", độ ồn bên em chưa có thông tin"
            stars = f", {p['energy_stars']} sao điện" if p.get("energy_stars") else ""
            lines.append(f"• {p['name']} — {price}{stars}{noise}.")
        return ("Dạ theo nhu cầu mình chia sẻ, em chốt 3 lựa chọn này ạ:\n\n"
                + "\n".join(lines)
                + "\n\nMẫu đầu cân bằng nhất với ưu tiên của mình; mẫu rẻ hơn tiết kiệm chi phí ban đầu"
                  " nhưng đánh đổi thông số; mẫu cao hơn bền và đầy đủ tiện ích hơn ạ.")
    if kind == "no_match":
        return ("Dạ với điều kiện hiện tại em chưa tìm được mẫu nào khớp hoàn toàn.\n\n"
                "Anh/chị có thể nới ngân sách hoặc diện tích một chút để em tìm lại giúp mình nhé ạ.")
    return "Dạ em là trợ lý tư vấn điện máy của Điện Máy Xanh, mình cần tư vấn sản phẩm nào em hỗ trợ liền ạ!"


async def stream_phrase(kind: str, context: dict) -> AsyncIterator[str]:
    """kind: ask | compare | no_match | off_topic. context: JSON đưa vào prompt."""
    if MOCK_LLM or kind == "off_topic":
        async for chunk in _mock_stream(_mock_phrase(kind, context)):
            yield chunk
        return
    user_msg = {
        "ask": "Hãy hỏi khách MỘT câu để lấy thông tin '{question_slot}'. Gợi ý cách hỏi: {ask_hint}. "
               "Số sản phẩm đang khớp: {candidate_count}. Thông tin đã có: {slots}",
        "compare": "So sánh và tư vấn top 3 sau cho khách (ưu tiên của khách: {priorities}). "
                   "Nêu trade-off giữa 3 mẫu. DATA (nguồn duy nhất được phép dùng): {products}",
        "no_match": "Không có sản phẩm khớp bộ lọc {slots}. Xin lỗi khách và đề xuất nới tiêu chí nào hợp lý.",
    }[kind].format(**{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                      for k, v in context.items()})
    llm = _get_llm(LLM_MODEL_LARGE, 0.3)
    async for chunk in llm.astream([("system", SALER_SYSTEM), ("user", user_msg)]):
        if chunk.content:
            yield chunk.content
