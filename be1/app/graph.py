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

from . import llm, ontology, product_repo, rag
from .config import COMPARE_THRESHOLD, RAG_MIN_SCORE, RAG_TOP_K
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
    # A product from the immediately preceding shortlist is a catalog request,
    # even when the customer also asks about its warranty.
    if state.get("selected_index") or state.get("wants_product_details"):
        return "retrieve"
    if state["intent_type"] == "policy":
        return "policy"
    if state["intent_type"] == "off_topic":
        return "off_topic"
    if not state.get("category"):
        return "off_topic"  # chưa biết khách muốn loại gì và câu nói không có tín hiệu
    return "retrieve"


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


def build_graph(*, checkpointer):
    g = StateGraph(AgentState)
    g.add_node("intent", intent_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("ask", ask_node)
    g.add_node("compare", compare_node)
    g.add_node("detail", detail_node)
    g.add_node("price_answer", price_answer_node)
    g.add_node("policy", policy_node)
    g.add_node("off_topic", off_topic_node)
    g.add_edge(START, "intent")
    g.add_conditional_edges("intent", route_after_intent,
                            {"retrieve": "retrieve", "policy": "policy", "off_topic": "off_topic"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"ask": "ask", "compare": "compare", "detail": "detail", "price_answer": "price_answer"})
    g.add_edge("ask", END)
    g.add_edge("compare", END)
    g.add_edge("detail", END)
    g.add_edge("price_answer", END)
    g.add_edge("policy", END)
    g.add_edge("off_topic", END)
    return g.compile(checkpointer=checkpointer)
