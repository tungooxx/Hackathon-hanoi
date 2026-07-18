"""LangGraph: intent -> retrieve -> (ask | compare) | off_topic.

Authenticated state persists through PostgreSQL; guest turns compile without
a checkpointer and are intentionally stateless.
Mọi output đẩy ra FE qua stream_mode="custom"; event type bắt đầu bằng "_"
là internal (log-only), main.py sẽ không forward cho client.
"""
import time
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from . import llm, ontology, product_repo, rag, tools
from .config import LLM_API_KEY, MOCK_LLM, RAG_MIN_SCORE, RAG_TOP_K
from .decision_gap import choose_next_question
from .filtering import apply_hard_filters
from .scoring import rank_top3


class AgentState(TypedDict, total=False):
    user_input: str
    category: str | None
    slots: dict[str, Any]
    priorities: list[str]
    ask_count: int
    asked_slots: list[str]
    intent_type: str
    candidates: list[dict]
    catalog_products: list[dict]
    total_in_category: int
    selected_index: int | None
    wants_product_details: bool
    price_order: str | None
    product_mentions: list[str]
    unknown_products: list[str]
    web_spec: dict[str, Any]
    enrich_pending: bool
    found_in_catalog: bool


async def intent_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    slots = dict(state.get("slots", {}))
    asked = list(state.get("asked_slots", []))
    ask_count = state.get("ask_count", 0)
    category = state.get("category")
    expected_question = None
    if category and asked:
        schema = {definition.name: definition for definition in ontology.get_slot_schema(category)}
        if definition := schema.get(asked[-1]):
            expected_question = {
                "slot": definition.name,
                "question": definition.ask_hint,
                "type": definition.question_type,
                "answers": definition.possible_answers,
            }
    result = await llm.extract_intent(
        state["user_input"], state.get("category"), state.get("slots", {}),
        expected_question=expected_question,
    )

    # Never trust a manual category map: resolve against category values that
    # actually exist in Elasticsearch. A real LLM may suggest a label, but ES
    # remains the source of truth.
    resolved_category = await product_repo.resolve_category(state["user_input"])
    if resolved_category:
        result.category = resolved_category
    elif category:
        # Keep the catalog category established in an earlier turn. LLM labels
        # are semantic guesses, not Elasticsearch identifiers.
        result.category = category
    else:
        result.category = None

    if result.intent_type == "new_topic" and result.category and result.category != category:
        # đổi category giữa chừng: reset slots trừ budget, reset đếm câu hỏi
        slots = {k: v for k, v in slots.items() if k == "budget_max"}
        asked, ask_count = [], 0
    if result.category:
        category = result.category

    slots.update(result.slot_dict())

    priorities = list(state.get("priorities", []))
    for p in result.priorities:
        if p not in priorities:
            priorities.append(p)

    w({"type": "_stage", "stage": "intent", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "_intent", "data": result.model_dump()})
    return {
        "intent_type": result.intent_type, "category": category, "slots": slots,
        "priorities": priorities, "asked_slots": asked, "ask_count": ask_count,
        "selected_index": result.selected_index,
        "wants_product_details": result.wants_product_details,
        "price_order": result.price_order,
        "product_mentions": result.product_mentions,
    }


async def retrieve_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    products = await product_repo.get_products(state["category"])
    candidates = apply_hard_filters(products, state["slots"])
    w({"type": "_stage", "stage": "retrieve", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "funnel_count", "count": len(candidates), "total": len(products),
       "filters": state["slots"]})
    return {"candidates": candidates, "catalog_products": products, "total_in_category": len(products)}


def route_after_intent(state: AgentState) -> str:
    # Khách đang trả lời câu hỏi nhu cầu của luồng "sản phẩm lạ" -> tiếp tục resolve.
    if state.get("enrich_pending"):
        return "resolve"
    # A product from the immediately preceding shortlist is a catalog request,
    # even when the customer also asks about its warranty.
    if state.get("selected_index") or state.get("wants_product_details"):
        return "retrieve"
    if state["intent_type"] == "policy":
        return "policy"
    # Lưới an toàn tất định: một từ khoá dịch vụ/chính sách rõ ràng (bảo hành, đổi trả,
    # giao hàng...) là câu hỏi CSKH, KHÔNG phải tra kho — kể cả khi model intent nhỏ đọc
    # nhầm 'bảo hành ip8' thành product_mentions. Đặt SAU gate selected_index/
    # wants_product_details ở trên nên 'bảo hành mẫu vừa chọn' vẫn ra chi tiết SP, không
    # bị nhánh 'sản phẩm lạ' cướp thành câu 'nới lỏng bộ lọc' vô nghĩa.
    if llm.looks_like_policy(state["user_input"]):
        return "policy"
    # Khách nêu tên/mã sản phẩm cụ thể là tín hiệu mua hàng rõ ràng -> tra kho trước
    # khi làm giàu từ web (kể cả khi phân loại ý định lỡ rơi vào off_topic).
    if state.get("product_mentions"):
        return "product_lookup"
    if state["intent_type"] == "off_topic":
        return "off_topic"
    if not state.get("category"):
        return "off_topic"  # chưa biết khách muốn loại gì và câu nói không có tín hiệu
    return "retrieve"


def route_after_product_lookup(state: AgentState) -> str:
    return "compare" if state.get("found_in_catalog") else "enrich"


def route_after_retrieve(state: AgentState) -> str:
    if not state["candidates"]:
        return "compare"  # compare_node xử lý case rỗng (no_match)
    if state.get("selected_index") or state.get("wants_product_details"):
        return "detail"
    if state.get("price_order"):
        return "price_answer"
    if state["intent_type"] == "force_answer":
        return "compare"
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"]
    )
    return "ask" if nq else "compare"


async def ask_node(state: AgentState) -> dict:
    w = get_stream_writer()
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"]
    )
    schema = {s.name: s for s in ontology.get_slot_schema(state["category"], state["catalog_products"])}
    w({"type": "question", "slot": nq.slot, "reason": nq.reason})
    t0 = time.perf_counter()
    async for chunk in llm.stream_phrase("ask", {
        "question_slot": nq.slot,
        "ask_hint": schema[nq.slot].ask_hint,
        "candidate_count": len(state["candidates"]),
        "slots": state["slots"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "ask_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "ask"})
    return {"ask_count": state["ask_count"] + 1, "asked_slots": state["asked_slots"] + [nq.slot]}


async def compare_node(state: AgentState) -> dict:
    w = get_stream_writer()
    if not state["candidates"]:
        async for chunk in llm.stream_phrase("no_match", {"slots": state["slots"]}):
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "no_match"})
        return {}
    top3 = rank_top3(state["candidates"], state["priorities"])
    w({"type": "product_cards", "products": top3})
    w({"type": "_context", "products": top3, "slots": state["slots"]})
    t0 = time.perf_counter()
    async for chunk in llm.stream_phrase("compare", {
        "products": top3, "priorities": state["priorities"] or ["gia_re"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "compare_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "compare"})
    return {}


async def detail_node(state: AgentState) -> dict:
    """Show a selected shortlist product from catalog data, never policy RAG."""
    w = get_stream_writer()
    shortlist = rank_top3(state["candidates"], state["priorities"])
    index = (state.get("selected_index") or 1) - 1
    if index >= len(shortlist):
        index = 0
    product = shortlist[index]
    w({"type": "product_cards", "products": [product]})
    w({"type": "_context", "product": product, "slots": state["slots"]})
    t0 = time.perf_counter()
    async for chunk in llm.stream_phrase("detail", {
        "product": product,
        "question": state["user_input"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "detail_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "detail"})
    return {}


async def price_answer_node(state: AgentState) -> dict:
    """Answer a direct cheapest/most-expensive question within the active filter."""
    w = get_stream_writer()
    priced = [product for product in state["candidates"] if product.get("price_sale") is not None]
    if not priced:
        async for chunk in llm.stream_phrase("no_match", {"slots": state["slots"]}):
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "price_answer"})
        return {}
    product = (
        max(priced, key=lambda item: item["price_sale"])
        if state["price_order"] == "highest"
        else min(priced, key=lambda item: item["price_sale"])
    )
    w({"type": "product_cards", "products": [product]})
    async for chunk in llm.stream_phrase("price_answer", {
        "product": product,
        "price_order": state["price_order"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "price_answer"})
    return {}


async def policy_node(state: AgentState) -> dict:
    """RAG: tìm chunk chính sách liên quan -> trả lời grounded. Điểm thấp -> thú nhận không có."""
    w = get_stream_writer()
    t0 = time.perf_counter()
    hits = await rag.search(state["user_input"], RAG_TOP_K)
    w({"type": "_stage", "stage": "policy_retrieve", "ms": round((time.perf_counter() - t0) * 1000)})

    if not hits or hits[0].score < RAG_MIN_SCORE:
        w({"type": "_policy_miss", "top_score": hits[0].score if hits else 0.0})
        async for chunk in llm.stream_phrase("policy_no_info", {}):
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "policy"})
        return {}

    hit_dicts = [{"title": h.title, "source": h.source, "text": h.text, "score": h.score} for h in hits]
    w({"type": "policy_sources",
       "sources": [{"title": h.title, "source": h.source, "score": h.score} for h in hits]})
    w({"type": "_context", "policy_hits": hit_dicts, "query": state["user_input"]})
    t1 = time.perf_counter()
    async for chunk in llm.stream_phrase("policy", {"question": state["user_input"], "hits": hit_dicts}):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "policy_phrase", "ms": round((time.perf_counter() - t1) * 1000)})
    w({"type": "done", "turn_type": "policy"})
    return {}


async def off_topic_node(state: AgentState) -> dict:
    w = get_stream_writer()
    async for chunk in llm.stream_phrase("off_topic", {}):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "off_topic"})
    return {}


# ---------------- nhánh "sản phẩm lạ": lookup -> enrich (web + hỏi) -> resolve ----------------

_TOOL_LABELS = {
    "web_search": "Đang tìm trên internet…",
    "fetch_product_specs": "Đang tra thông số sản phẩm trên web…",
    "search_catalog": "Đang tra trong kho…",
    "filter_catalog": "Đang lọc các mẫu phù hợp…",
}


def _emit_tool(w, phase: str, name: str, payload) -> None:
    """Stream trạng thái tool ra FE: start (running) + end (done + count).

    FE dùng để dựng bảng 'đang suy nghĩ' (bật/tắt bằng VITE_DEBUG). Event tool_call/
    tool_result KHÔNG có tiền tố '_' nên luôn được forward; production tắt hiển thị ở FE.
    """
    if phase == "start":
        w({"type": "tool_call", "tool": name, "status": "running",
           "label": _TOOL_LABELS.get(name, name), "args": payload})
    else:
        n = len(payload) if isinstance(payload, list) else None
        w({"type": "tool_result", "tool": name, "status": "done", "count": n})


async def product_lookup_node(state: AgentState) -> dict:
    """Tra tên/mã sản phẩm khách nêu trong Elasticsearch trước khi phán 'không có'."""
    w = get_stream_writer()
    mentions = state.get("product_mentions") or []
    query = mentions[0] if mentions else state["user_input"]
    t0 = time.perf_counter()
    _emit_tool(w, "start", "search_catalog", {"query": query})
    hits = await tools.search_catalog(query, state.get("category"))
    _emit_tool(w, "end", "search_catalog", hits)
    w({"type": "_stage", "stage": "product_lookup", "ms": round((time.perf_counter() - t0) * 1000)})
    if hits:
        category = state.get("category") or hits[0].get("category")
        return {"candidates": hits[:20], "catalog_products": hits,
                "category": category, "found_in_catalog": True}
    return {"unknown_products": mentions or [query], "found_in_catalog": False}


async def _run_resolve(state: AgentState, w) -> dict:
    """Đối chiếu nhu cầu với thông số web -> tra lại kho -> trả SP đúng hoặc top tương đương."""
    web_spec = state.get("web_spec") or {}
    slots = dict(state.get("slots", {}))
    for k, v in (web_spec.get("catalog_slots") or {}).items():
        slots.setdefault(k, v)  # slot khách nói thắng slot suy từ web
    category = state.get("category") or web_spec.get("category")
    priorities = state.get("priorities", [])
    product_name = web_spec.get("product_name") or (state.get("unknown_products") or [""])[0]

    found_exact: list[dict] = []
    equivalents: list[dict] = []
    agent_ok = False
    agent_final = ""  # câu chốt web-grounded của agent (vd "không có iPhone 9")
    if not (MOCK_LLM or not LLM_API_KEY):
        # tool-calling THẬT: agent tự quyết web_search/search_catalog/filter_catalog (bounded).
        # Provider lỗi -> rơi về orchestration tất định bên dưới, không sập lượt chat.
        try:
            agent = await llm.run_tool_agent(
                f"Khách hỏi sản phẩm: {product_name}. Nhu cầu (slots): {slots}. "
                f"Ưu tiên: {priorities}. Category kho dự kiến: {category}. "
                f"Thông số web đã có: {web_spec.get('key_specs')}.",
                on_tool=lambda phase, name, payload: _emit_tool(w, phase, name, payload),
            )
            results = agent["tool_results"]
            sc = [r for r in results.get("search_catalog", []) if isinstance(r, list) and r]
            fc = [r for r in results.get("filter_catalog", []) if isinstance(r, list) and r]
            found_exact = sc[-1] if sc else []
            equivalents = fc[-1] if fc else []
            agent_final = (agent.get("final_text") or "").strip()
            agent_ok = True
        except Exception as exc:
            w({"type": "_tool_result", "tool": "enrich_agent", "error": str(exc)[:200]})

    if not agent_ok and not found_exact and not equivalents:
        # orchestration tất định: tra lại kho theo tên -> không có thì lọc tương đương
        found_exact = await tools.search_catalog(product_name, category)
    if not found_exact and not equivalents and category:
        equivalents = await tools.filter_catalog(category, slots, priorities)

    products = (found_exact or equivalents)[:3]
    if not products:
        # Không có SP trong kho: nếu agent đã web_search và tự chốt (vd "Apple không có
        # iPhone 9", "bên em không kinh doanh mặt hàng này") -> trả LỜI CHỐT WEB-GROUNDED
        # đó, thay vì câu no_match "nới lỏng bộ lọc" vô nghĩa với sản phẩm không tồn tại.
        if agent_final:
            w({"type": "text_chunk", "content": agent_final})
            w({"type": "done", "turn_type": "enrich"})
            return {"enrich_pending": False}
        async for chunk in llm.stream_phrase("no_match", {"slots": slots}):
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "enrich"})
        return {"enrich_pending": False}

    w({"type": "product_cards", "products": products})
    w({"type": "_context", "products": products, "slots": slots, "web_spec": web_spec})
    if found_exact:
        intro = f"Dạ mẫu {product_name} bên em có ạ, em gửi thông tin để mình tham khảo nhé."
    else:
        intro = (f"Dạ mẫu {product_name} anh/chị hỏi hiện bên em chưa có ạ, "
                 f"em xin gợi ý vài mẫu tương đương hợp nhu cầu mình nhất:")
    w({"type": "text_chunk", "content": intro + "\n\n"})
    async for chunk in llm.stream_phrase("compare", {
        "products": products, "priorities": priorities or ["gia_re"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "enrich"})
    return {"enrich_pending": False, "candidates": products}


async def enrich_node(state: AgentState) -> dict:
    """SP lạ: tra thông số trên web (tool) SONG SONG với hỏi nhu cầu; đủ nhu cầu thì resolve luôn."""
    w = get_stream_writer()
    unknown = (state.get("unknown_products") or [state["user_input"]])[0]
    w({"type": "enrich_note",
       "message": f"Dạ mẫu '{unknown}' hiện chưa có sẵn trong kho, để em tra cứu thêm giúp mình ạ."})
    t0 = time.perf_counter()
    _emit_tool(w, "start", "fetch_product_specs", {"product_name": unknown})
    web_spec = await tools.fetch_product_specs(unknown)
    _emit_tool(w, "end", "fetch_product_specs", web_spec)
    w({"type": "_stage", "stage": "web_fetch", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "web_specs", "product": unknown, "spec": web_spec})

    slots = dict(state.get("slots", {}))
    priorities = state.get("priorities", [])
    # Category phải là NHÃN thật trong Elasticsearch (không phải mã "may_lanh" web suy ra).
    category = state.get("category")
    if not category:
        hint = f"{state['user_input']} {web_spec.get('summary', '')} {web_spec.get('category', '')}"
        category = await product_repo.resolve_category(hint) or web_spec.get("category")
    needs_present = bool(slots.get("budget_max") or slots.get("area_m2") or priorities)
    updates: dict[str, Any] = {"web_spec": web_spec, "category": category}

    if not needs_present and category:
        products = await product_repo.get_products(category)
        nq = choose_next_question(category, slots, state.get("asked_slots", []), products, priorities)
        if nq:
            schema = {s.name: s for s in ontology.get_slot_schema(category, products)}
            w({"type": "question", "slot": nq.slot, "reason": nq.reason})
            async for chunk in llm.stream_phrase("ask", {
                "question_slot": nq.slot, "ask_hint": schema[nq.slot].ask_hint,
                "candidate_count": len(products), "slots": slots,
            }):
                w({"type": "text_chunk", "content": chunk})
            w({"type": "done", "turn_type": "enrich_ask"})
            updates.update({
                "enrich_pending": True,
                "ask_count": state.get("ask_count", 0) + 1,
                "asked_slots": state.get("asked_slots", []) + [nq.slot],
            })
            return updates

    # nhu cầu đã đủ (hoặc chưa xác định được category để hỏi) -> resolve ngay trong turn này
    resolve_updates = await _run_resolve({**state, **updates}, w)
    return {**updates, **resolve_updates}


async def resolve_node(state: AgentState) -> dict:
    """Turn sau khi khách trả lời nhu cầu: chốt bằng vòng lặp tool-calling + tra lại kho."""
    w = get_stream_writer()
    return await _run_resolve(state, w)


def build_graph(*, checkpointer):
    g = StateGraph(AgentState)
    g.add_node("intent", intent_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("ask", ask_node)
    g.add_node("compare", compare_node)
    g.add_node("detail", detail_node)
    g.add_node("price_answer", price_answer_node)
    g.add_node("product_lookup", product_lookup_node)
    g.add_node("enrich", enrich_node)
    g.add_node("resolve", resolve_node)
    g.add_node("policy", policy_node)
    g.add_node("off_topic", off_topic_node)
    g.add_edge(START, "intent")
    g.add_conditional_edges("intent", route_after_intent,
                            {"retrieve": "retrieve", "policy": "policy", "off_topic": "off_topic",
                             "product_lookup": "product_lookup", "resolve": "resolve"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"ask": "ask", "compare": "compare", "detail": "detail", "price_answer": "price_answer"})
    g.add_conditional_edges("product_lookup", route_after_product_lookup,
                            {"compare": "compare", "enrich": "enrich"})
    g.add_edge("ask", END)
    g.add_edge("compare", END)
    g.add_edge("detail", END)
    g.add_edge("price_answer", END)
    g.add_edge("enrich", END)
    g.add_edge("resolve", END)
    g.add_edge("policy", END)
    g.add_edge("off_topic", END)
    return g.compile(checkpointer=checkpointer)
