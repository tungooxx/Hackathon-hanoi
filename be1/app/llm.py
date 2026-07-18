"""2 lượt LLM/turn: extract_intent (structured, model nhỏ) + stream_phrase (streaming, model lớn).

MOCK_LLM=1 -> regex/template, chạy full luồng không cần API key.
"""
import asyncio
import json
import re
from collections.abc import AsyncIterator

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_LARGE, LLM_MODEL_SMALL, MOCK_LLM
from .schemas import IntentResult
from .tracing import lf_config

INTENT_SYSTEM = """Bạn là bộ phân tích ý định cho trợ lý bán hàng Điện Máy Xanh.
Trích xuất từ tin nhắn khách (tiếng Việt có thể sai chính tả, không dấu, viết tắt).
Ngữ cảnh hội thoại: category hiện tại = {category}, thông tin đã có = {slots}.

Quy tắc:
- intent_type: "new_topic" nếu khách chuyển sang loại sản phẩm khác; "same_topic" nếu bổ sung \
thông tin hoặc hỏi mẫu vừa được gợi ý; "off_topic" nếu không liên quan mua sắm điện máy; "force_answer" nếu khách muốn \
được gợi ý/chốt ngay ("tư vấn luôn đi", "cứ gợi ý đi", "sao cũng được"); "policy" nếu khách \
hỏi về CHÍNH SÁCH/QUY ĐỊNH cửa hàng (bảo hành, đổi trả, hoàn tiền/trả hàng, giao hàng, lắp đặt, \
khui hộp, điều khoản sử dụng, xử lý dữ liệu cá nhân/bảo mật, nội quy) — kể cả khi có nhắc tên sản phẩm.
- budget_max đổi về VND: "10tr"/"10 triệu" -> 10000000. "tầm"/"khoảng" vẫn tính là budget_max.
- product_mentions: chép NGUYÊN VĂN tên/mã sản phẩm khách gõ, không sửa chính tả.
- Nếu khách nói "loại/mẫu số 1", "máy 1", "mẫu đầu", hoặc yêu cầu thông tin chi tiết về một mẫu
  trong danh sách vừa gợi ý: đặt selected_index (1-3), wants_product_details=true và intent_type=same_topic.
- "Bảo hành" của mẫu khách vừa chọn là thông tin sản phẩm, KHÔNG phải policy. Chỉ dùng intent_type=policy
  khi khách hỏi chính sách chung của cửa hàng, không gắn với mẫu đang chọn.
- priorities theo thứ tự khách nhắc: tiết kiệm điện->tiet_kiem_dien, êm/ít ồn->it_on, rẻ->gia_re.

Ví dụ:
"mya lanh cho fong 15m2 tam 8tr" -> category=may_lanh, area_m2=15, budget_max=8000000, intent_type=new_topic
"thoi co gi tu van luon di" -> intent_type=force_answer
"thông tin loại 1 và bảo hành" -> selected_index=1, wants_product_details=true, intent_type=same_topic
"may lanh nay bao hanh bao lau" -> wants_product_details=true, intent_type=same_topic
"chinh sach doi tra the nao" -> intent_type=policy
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

POLICY_SYSTEM = """Bạn là nhân viên CSKH Điện Máy Xanh — thân thiện, gọi khách "anh/chị", xưng "em".
Trả lời câu hỏi của khách về CHÍNH SÁCH cửa hàng.
Quy tắc SẮT (vi phạm = sa thải):
- CHỈ dùng thông tin trong phần TRÍCH CHÍNH SÁCH được cung cấp. TUYỆT ĐỐI không bịa, không dùng \
kiến thức ngoài, không suy diễn ngoài trích dẫn.
- Nếu trích dẫn KHÔNG chứa câu trả lời -> nói thẳng "phần này bên em chưa có thông tin trong chính \
sách ạ, anh/chị vui lòng liên hệ tổng đài 1800.1060 để được hỗ trợ chính xác nhé", KHÔNG đoán.
- Nêu ĐÚNG con số/điều kiện (số ngày, %, phí, mốc thời gian...) y như trong trích dẫn.
- Nhắc tên chính sách nguồn một cách tự nhiên khi trả lời.
- Trả lời như đang NHẮN TIN: chia 2-4 tin ngắn, mỗi tin cách nhau ĐÚNG MỘT dòng trống, tổng ~120 từ."""


def _get_llm(model: str, temperature: float):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model, base_url=LLM_BASE_URL, api_key=LLM_API_KEY,
        temperature=temperature, timeout=30,
    )


# ---------------- intent ----------------

_POLICY_KW = [
    "bảo hành", "bao hanh", "đổi trả", "doi tra", "hoàn tiền", "hoan tien", "trả hàng", "tra hang",
    "giao hàng", "giao hang", "lắp đặt", "lap dat", "khui hộp", "khui hop", "điều khoản", "dieu khoan",
    "dữ liệu cá nhân", "du lieu ca nhan", "bảo mật", "bao mat", "nội quy", "noi quy",
    "chính sách", "chinh sach", "quy định", "quy dinh",
]


def _mock_intent(text: str, category: str | None, expected_question: dict | None = None) -> IntentResult:
    low = text.lower()
    cat = None  # Category is resolved against real Elasticsearch data in graph.py.
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
    is_policy = any(k in low for k in _POLICY_KW)
    selected_index = None
    if m := re.search(r"(?:loại|loai|mẫu|mau|máy|may)\s*(?:số\s*)?([1-3])\b", low):
        selected_index = int(m.group(1))
    elif re.search(r"mẫu đầu|mau dau|loại đầu|loai dau", low):
        selected_index = 1
    wants_details = bool(selected_index or re.search(r"thông tin|thong tin|chi tiết|chi tiet", low))
    if force:
        itype = "force_answer"
    elif wants_details:
        # A reference to an item in the preceding shortlist is not a general
        # store-policy request, even if the customer also asks about warranty.
        itype = "same_topic"
    elif is_policy and not slots and not wants_details and selected_index is None:
        # hỏi chính sách (không kèm ngân sách/diện tích = không phải đang lọc sản phẩm)
        return IntentResult(intent_type="policy", category=None, priorities=[])
    elif cat and cat != category:
        itype = "new_topic"
    elif slots or prios or re.search(r"mua|cần|can|tìm|tim", low):
        itype = "same_topic"
    else:
        # mock không hiểu ngữ nghĩa: không có tín hiệu nào -> off_topic
        # (LLM thật phân biệt được "phòng ngủ" là trả lời câu hỏi vs câu lạc đề)
        itype = "off_topic"
    result = IntentResult(
        intent_type=itype, category=cat, priorities=prios,
        budget_max=slots.get("budget_max"), area_m2=slots.get("area_m2"),
        selected_index=selected_index, wants_product_details=wants_details,
    )
    if expected_question and (slot := expected_question.get("slot")) in IntentResult.model_fields:
        normalized = re.sub(r"\s+", " ", low).strip()
        if normalized in {"có", "co", "cần", "can", "đúng", "dung", "không", "khong", "ko"}:
            return result.model_copy(update={slot: normalized not in {"không", "khong", "ko"}, "intent_type": "same_topic"})
    return result


async def extract_intent(
    text: str,
    category: str | None,
    slots: dict,
    expected_question: dict | None = None,
) -> IntentResult:
    if MOCK_LLM:
        return _mock_intent(text, category, expected_question)
    llm = _get_llm(LLM_MODEL_SMALL, 0.0).with_structured_output(IntentResult)
    system = INTENT_SYSTEM.format(category=category or "chưa có", slots=json.dumps(slots, ensure_ascii=False))
    if expected_question:
        system += (
            "\nThe customer is replying to this ontology question: "
            f"{json.dumps(expected_question, ensure_ascii=False)}. "
            "Interpret the reply as the answer to that exact question and populate its slot. "
            "Do not infer values for any other slot."
        )
    system += (
        "\nWhen the customer asks for the most expensive/highest priced option in the current list, "
        "set price_order='highest'. For cheapest/lowest priced, set price_order='lowest'."
    )
    return await llm.ainvoke([("system", system), ("user", text)], config=lf_config("intent"))


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
        # Dynamic ontology concepts must never leak internal slot names to a
        # customer. Their Vietnamese question label is the fallback wording.
        return asks.get(slot, f"Dạ để em tư vấn sát hơn: {context['ask_hint']}")
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
    if kind == "detail":
        product = context["product"]
        price = f"{product['price_sale']:,.0f}đ".replace(",", ".") if product.get("price_sale") else "bên em chưa có giá"
        warranty = product.get("warranty_parts") or "phần bảo hành bên em chưa có thông tin"
        return f"Dạ mẫu anh/chị chọn là {product['name']}, giá hiện tại {price}.\n\nBảo hành: {warranty}."
    if kind == "price_answer":
        product = context["product"]
        price = product.get("price_sale")
        return f"Dạ {product['name']} là mẫu {'đắt' if context['price_order'] == 'highest' else 'rẻ'} nhất, giá {price:,.0f}đ.".replace(",", ".")
    elif kind == "policy":
        top = context["hits"][0]
        snippet = top["text"].split("\n", 1)[-1].strip()[:400]  # bỏ dòng header [title]
        return (f"Dạ theo {top['title']} của bên em:\n\n"
                f"{snippet}\n\n"
                f"Anh/chị cần em nói rõ thêm phần nào không ạ?")
    if kind == "policy_no_info":
        return ("Dạ phần này em chưa tìm thấy trong chính sách hiện có của bên em ạ.\n\n"
                "Anh/chị vui lòng liên hệ tổng đài 1800.1060 để được hỗ trợ chính xác nhất nhé ạ.")
    return "Dạ em là trợ lý tư vấn điện máy của Điện Máy Xanh, mình cần tư vấn sản phẩm nào em hỗ trợ liền ạ!"


async def stream_phrase(kind: str, context: dict) -> AsyncIterator[str]:
    """kind: ask | compare | detail | no_match | off_topic | policy | policy_no_info."""
    if MOCK_LLM or kind in ("off_topic", "policy_no_info"):
        async for chunk in _mock_stream(_mock_phrase(kind, context)):
            yield chunk
        return
    if kind == "policy":
        system = POLICY_SYSTEM
        chunks_str = "\n\n---\n\n".join(h["text"] for h in context["hits"])
        user_msg = (f"Câu hỏi của khách: {context['question']}\n\n"
                    f"TRÍCH CHÍNH SÁCH (nguồn DUY NHẤT được phép dùng):\n{chunks_str}")
    else:
        system = SALER_SYSTEM
        user_msg = {
            "ask": "Hãy hỏi khách MỘT câu để lấy thông tin '{question_slot}'. Gợi ý cách hỏi: {ask_hint}. "
                   "Số sản phẩm đang khớp: {candidate_count}. Thông tin đã có: {slots}",
            "compare": "So sánh và tư vấn top 3 sau cho khách (ưu tiên của khách: {priorities}). "
                       "Nêu trade-off giữa 3 mẫu. DATA (nguồn duy nhất được phép dùng): {products}",
            "detail": "Trả lời tự nhiên về MỘT sản phẩm khách đã chọn. Giải thích dễ hiểu các thông số có dữ liệu, "
                      "đặc biệt câu hỏi của khách. Nếu warranty_parts trống thì nói rõ catalog chưa có thông tin; "
                      "không dùng chính sách chung của cửa hàng. DATA (nguồn duy nhất được phép dùng): {product}",
            "no_match": "Không có sản phẩm khớp bộ lọc {slots}. Xin lỗi khách và đề xuất nới tiêu chí nào hợp lý. "
                        "TUYỆT ĐỐI không nêu bất kỳ con số/thông số sản phẩm nào (turn này không có dữ liệu sản phẩm).",
        }[kind].format(**{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                          for k, v in context.items()})
    llm = _get_llm(LLM_MODEL_LARGE, 0.2 if kind == "policy" else 0.3)
    msgs = [("system", system), ("user", user_msg)]
    cfg = lf_config(f"phrase_{kind}")
    for attempt in range(3):  # FPT thỉnh thoảng 404/timeout lúc mở stream -> retry khi CHƯA yield
        started = False
        try:
            async for chunk in llm.astream(msgs, config=cfg):
                if chunk.content:
                    started = True
                    yield chunk.content
            return
        except Exception:
            if started or attempt == 2:  # đã stream dở -> không retry (tránh lặp text)
                raise
