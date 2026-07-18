"""LangGraph: intent -> retrieve -> (ask | compare) | off_topic.

State persist theo session_id qua checkpointer (thay cho "History agent").
Mọi output đẩy ra FE qua stream_mode="custom"; event type bắt đầu bằng "_"
là internal (log-only), main.py sẽ không forward cho client.
"""
import time
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from . import be2_client, llm, ontology_stub, rag
from .config import COMPARE_THRESHOLD, MAX_ASK_TURNS, RAG_MIN_SCORE, RAG_TOP_K
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
    total_in_category: int


async def intent_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    result = await llm.extract_intent(
        state["user_input"], state.get("category"), state.get("slots", {})
    )
    slots = dict(state.get("slots", {}))
    asked = list(state.get("asked_slots", []))
    ask_count = state.get("ask_count", 0)
    category = state.get("category")

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
    }


async def retrieve_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    products = await be2_client.get_products(state["category"])
    candidates = apply_hard_filters(products, state["slots"])
    w({"type": "_stage", "stage": "retrieve", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "funnel_count", "count": len(candidates), "total": len(products),
       "filters": state["slots"]})
    return {"candidates": candidates, "total_in_category": len(products)}


def route_after_intent(state: AgentState) -> str:
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
    if state["intent_type"] == "force_answer":
        return "compare"
    if len(state["candidates"]) <= COMPARE_THRESHOLD or state["ask_count"] >= MAX_ASK_TURNS:
        return "compare"
    nq = ontology_stub.suggest_next_question(
        state["category"], state["slots"], state["asked_slots"], state["candidates"]
    )
    return "ask" if nq else "compare"


async def ask_node(state: AgentState) -> dict:
    w = get_stream_writer()
    nq = ontology_stub.suggest_next_question(
        state["category"], state["slots"], state["asked_slots"], state["candidates"]
    )
    schema = {s.name: s for s in ontology_stub.get_slot_schema(state["category"])}
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


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("intent", intent_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("ask", ask_node)
    g.add_node("compare", compare_node)
    g.add_node("policy", policy_node)
    g.add_node("off_topic", off_topic_node)
    g.add_edge(START, "intent")
    g.add_conditional_edges("intent", route_after_intent,
                            {"retrieve": "retrieve", "policy": "policy", "off_topic": "off_topic"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"ask": "ask", "compare": "compare"})
    g.add_edge("ask", END)
    g.add_edge("compare", END)
    g.add_edge("policy", END)
    g.add_edge("off_topic", END)
    return g.compile(checkpointer=MemorySaver())


graph = build_graph()
