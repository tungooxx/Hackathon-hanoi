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

from . import fulfillment, llm, ontology, product_repo, rag
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
    selected_sku: str | None
    wants_product_details: bool
    price_order: str | None
    catalog_lookup_failed: bool
    explicit_product: dict[str, Any] | None
    question_schema: list[Any]
    category_candidates: list[str]
    fulfillment_context: dict[str, str]
    awaiting_fulfillment: bool
    fulfillment_candidates: list[str]
    conversation_history: list[dict[str, str]]
    catalog_preferences: list[dict[str, str]]


def _customer_visible_slots(slots: dict[str, Any], schema: list[Any] | None = None) -> dict[str, Any]:
    """Never expose runtime IDs or executor sentinels in the UI funnel."""
    visible = {
        key: value for key, value in slots.items()
        if not key.startswith("Q_RUNTIME_") and value != ontology._SKIP_ANSWER
    }
    for definition in schema or []:
        value = slots.get(definition.name)
        if value is None or value == ontology._SKIP_ANSWER:
            continue
        if definition.maps_to_field.startswith("attributes."):
            visible[definition.maps_to_field.split(".", 1)[1]] = value
    return visible


async def intent_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    slots = dict(state.get("slots", {}))
    asked = list(state.get("asked_slots", []))
    ask_count = state.get("ask_count", 0)
    fulfillment_context = dict(state.get("fulfillment_context", {}))
    awaiting_fulfillment = state.get("awaiting_fulfillment", False)
    fulfillment_candidates: list[str] = []
    history = list(state.get("conversation_history", []))
    catalog_preferences = list(state.get("catalog_preferences", []))
    category = state.get("category")
    expected_question = None
    expected_definition = None
    if category and asked:
        schema = {definition.name: definition for definition in (
            state.get("question_schema") or ontology.get_slot_schema(category)
        )}
        if definition := schema.get(asked[-1]):
            expected_definition = definition
            expected_question = {
                "slot": definition.name,
                "question": definition.ask_hint,
                "type": definition.question_type,
                "answers": definition.possible_answers,
                "field": definition.maps_to_field,
                "operation": definition.operation,
            }
    result = await llm.extract_intent(
        state["user_input"], state.get("category"), state.get("slots", {}),
        expected_question=expected_question, conversation_history=history,
    )
    history = [*history, {"role": "user", "content": state["user_input"]}][-8:]
    if awaiting_fulfillment:
        required_key = fulfillment.fulfillment_provider.required_context(fulfillment_context)
        if required_key:
            resolver = getattr(fulfillment.fulfillment_provider, "resolve_region", None)
            resolution = resolver(state["user_input"]) if resolver else None
            if resolution and resolution.region:
                fulfillment_context[required_key] = resolution.region
            elif resolution:
                fulfillment_candidates = resolution.candidates
    normalized_active_number = result.active_answer_numeric_value
    if (expected_definition and expected_definition.maps_to_field in {"price_sale", "price_original"}
            and (result.budget_max is not None or normalized_active_number is not None)):
        normalized_budget = result.budget_max if result.budget_max is not None else normalized_active_number
        result = result.model_copy(update={
            "budget_max": normalized_budget,
            "ontology_answers": {**result.ontology_answers, expected_definition.name: normalized_budget},
        })

    # Never trust a manual category map: resolve against category values that
    # actually exist in Elasticsearch. A real LLM may suggest a label, but ES
    # remains the source of truth.
    catalog_lookup_failed = False
    category_candidates: list[str] = []
    try:
        # Resolve against the real category registry even during an active
        # question, because customers may explicitly change product type.
        resolved_category, category_candidates = await product_repo.resolve_category_candidates(state["user_input"])
        # A real category label inside a short answer may also name the feature
        # being discussed (for example "loa lớn" while answering an audio
        # question). Treat it as an answer when that catalog label overlaps the
        # active field/question; otherwise it is a generic, catalog-grounded
        # topic switch even if the small intent model missed it.
        if (expected_question and resolved_category and category
                and resolved_category != category and not result.active_question_override):
            active_text = product_repo._normal(
                f"{expected_question.get('question', '')} {expected_question.get('field', '')}"
            )
            category_tokens = set(product_repo._normal(resolved_category).split())
            if category_tokens & set(active_text.split()):
                resolved_category, category_candidates = None, []
        # The LLM may recognize an abbreviation ("tv" -> "tivi") that is
        # not a literal substring of the message. Its guess is accepted only
        # after this second lookup validates it against actual ES categories.
        if not resolved_category and not category_candidates and result.category and not expected_question:
            resolved_category, category_candidates = await product_repo.resolve_category_candidates(result.category)
    except Exception:
        # Category discovery depends on Elasticsearch, but a transient search
        # outage must not discard an established conversation or turn a reply
        # to an active ontology question into an off-topic message.
        resolved_category = None
        catalog_lookup_failed = True
    if resolved_category:
        result.category = resolved_category
    elif category:
        # Keep the catalog category established in an earlier turn. LLM labels
        # are semantic guesses, not Elasticsearch identifiers.
        result.category = category
    else:
        result.category = None

    # Structured output has a fixed schema whereas ontology concept IDs are
    # dynamic.  If the model fails to emit the requested dynamic dictionary
    # key, the active-question state is still authoritative: a short reply
    # such as "không" belongs to that question, not to the off-topic route.
    # An explicit category change and a policy request remain higher-priority
    # intents and are never overwritten here.
    if expected_question and (expected_slot := expected_question.get("slot")):
        answered = expected_slot in result.ontology_answers
        switched_category = bool(resolved_category and category and resolved_category != category)
        if (not answered and not switched_category and not result.active_question_override
                and result.intent_type not in {"policy"}):
            result = result.model_copy(update={
                "intent_type": "same_topic",
                "ontology_answers": {**result.ontology_answers, expected_slot: state["user_input"]},
            })

    # Do not let a vague reply become a fake filter.  The active schema and
    # current catalog decide whether the answer is executable; the LLM only
    # supplies language understanding.
    if expected_definition and expected_definition.name in result.ontology_answers:
        # Preserve operators and qualifiers from the customer's actual words
        # ("trở lên", "dưới", "khoảng"), which a semantic LLM may omit when
        # returning a normalized answer label. Price is the exception because
        # intent extraction already converts millions/thousands to VND.
        active_value: Any = state["user_input"]
        if expected_definition.question_type == "numeric" and normalized_active_number is not None:
            active_value = normalized_active_number
        if (expected_definition.maps_to_field in {"price_sale", "price_original"}
                and result.budget_max is not None):
            active_value = result.budget_max
        filter_ok, preference_ok, status = ontology.answer_status(
            expected_definition,
            active_value,
            state.get("catalog_products", []),
            wants_filter=result.active_answer_filter,
            preference=result.active_answer_preference,
            skip=result.active_answer_skip,
            clarify=result.active_answer_clarify,
            boolean_value=result.active_answer_boolean_value,
        )
        if status == "unresolved":
            answers = dict(result.ontology_answers)
            answers.pop(expected_definition.name, None)
            result = result.model_copy(update={"ontology_answers": answers, "intent_type": "same_topic"})
            # Let Decision-Gap ask the same question again rather than moving
            # on as though the customer had supplied a preference.
            if asked and asked[-1] == expected_definition.name:
                asked.pop()
        elif status == "skip":
            answers = dict(result.ontology_answers)
            answers[expected_definition.name] = ontology._SKIP_ANSWER
            result = result.model_copy(update={"ontology_answers": answers, "intent_type": "same_topic"})
        elif status == "resolved":
            answers = dict(result.ontology_answers)
            if filter_ok:
                if expected_definition.question_type == "boolean" and result.active_answer_boolean_value is not None:
                    answers[expected_definition.name] = (
                        ontology._BOOLEAN_TRUE if result.active_answer_boolean_value else ontology._BOOLEAN_FALSE
                    )
                else:
                    answers[expected_definition.name] = active_value
                result = result.model_copy(update={"ontology_answers": answers, "intent_type": "same_topic"})
            else:
                answers[expected_definition.name] = ontology._SKIP_ANSWER
                result = result.model_copy(update={"ontology_answers": answers, "intent_type": "same_topic"})
            direction = result.active_answer_preference
            if preference_ok and direction:
                preference = {"field": expected_definition.maps_to_field, "direction": direction}
                if preference not in catalog_preferences:
                    catalog_preferences.append(preference)

    if result.intent_type == "new_topic" and result.category and result.category != category:
        # đổi category giữa chừng: reset slots trừ budget, reset đếm câu hỏi
        slots = {k: v for k, v in slots.items() if k == "budget_max"}
        asked, ask_count = [], 0
    if result.category:
        category = result.category

    slots.update(result.slot_dict())
    # Dynamic ontology concepts are returned by the LLM under their exact
    # concept ID, so new categories need no Pydantic field or Python mapping.
    slots.update(result.ontology_answers)

    priorities = list(state.get("priorities", []))
    for p in result.priorities:
        if p not in priorities:
            priorities.append(p)

    w({"type": "_stage", "stage": "intent", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "_intent", "data": result.model_dump()})
    return {
        "intent_type": result.intent_type, "category": category, "slots": slots,
        "priorities": priorities, "asked_slots": asked, "ask_count": ask_count,
        "selected_index": (
            result.selected_index if result.selected_index is not None
            else state.get("selected_index") if awaiting_fulfillment else None
        ),
        "wants_product_details": result.wants_product_details,
        "price_order": result.price_order,
        "catalog_lookup_failed": catalog_lookup_failed,
        "category_candidates": category_candidates,
        "fulfillment_context": fulfillment_context,
        "awaiting_fulfillment": awaiting_fulfillment,
        "fulfillment_candidates": fulfillment_candidates,
        "conversation_history": history,
        "catalog_preferences": catalog_preferences,
    }


async def retrieve_node(state: AgentState) -> dict:
    w = get_stream_writer()
    t0 = time.perf_counter()
    try:
        products = await product_repo.get_products(state["category"])
        question_schema = await ontology.get_runtime_slot_schema(state["category"], products)
    except Exception:
        w({"type": "_stage", "stage": "retrieve", "ms": round((time.perf_counter() - t0) * 1000)})
        return {"catalog_lookup_failed": True, "candidates": [], "catalog_products": []}
    candidates = apply_hard_filters(products, state["slots"])
    candidates = ontology.apply_ontology_filters(state["category"], candidates, state["slots"], question_schema)
    explicit_product = product_repo.find_named_product(candidates, state["user_input"])
    w({"type": "_stage", "stage": "retrieve", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "funnel_count", "count": len(candidates), "total": len(products),
       "filters": _customer_visible_slots(state["slots"], question_schema)})
    return {
        "candidates": candidates, "catalog_products": products, "total_in_category": len(products),
        "explicit_product": explicit_product, "question_schema": question_schema,
        "catalog_lookup_failed": False,
    }


def route_after_intent(state: AgentState) -> str:
    if state.get("awaiting_fulfillment"):
        if state.get("fulfillment_candidates"):
            return "fulfillment_clarify"
        if fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
            return "fulfillment_prompt"
        return "fulfillment_check"
    # A product from the immediately preceding shortlist is a catalog request,
    # even when the customer also asks about its warranty.
    if state.get("selected_index") or state.get("wants_product_details"):
        return "retrieve"
    if state["intent_type"] == "policy":
        return "policy"
    if state.get("category_candidates"):
        return "clarify_category"
    if state.get("catalog_lookup_failed"):
        return "catalog_unavailable"
    if state["intent_type"] == "off_topic":
        return "off_topic"
    if not state.get("category"):
        return "off_topic"  # chưa biết khách muốn loại gì và câu nói không có tín hiệu
    return "retrieve"


def route_after_retrieve(state: AgentState) -> str:
    if state.get("catalog_lookup_failed"):
        return "catalog_unavailable"
    if not state["candidates"]:
        return "compare"  # compare_node xử lý case rỗng (no_match)
    if state.get("explicit_product") or state.get("selected_index") or state.get("wants_product_details"):
        if fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
            return "fulfillment_prompt"
        return "detail"
    if state.get("price_order"):
        return "price_answer"
    if state["intent_type"] == "force_answer":
        return "compare"
    started = time.perf_counter()
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"],
        state.get("question_schema"), state.get("catalog_preferences"),
    )
    get_stream_writer()({"type": "_stage", "stage": "decision_gap", "ms": round((time.perf_counter() - started) * 1000)})
    return "ask" if nq else "compare"


async def ask_node(state: AgentState) -> dict:
    w = get_stream_writer()
    decision_started = time.perf_counter()
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"],
        state.get("question_schema"), state.get("catalog_preferences"),
    )
    w({"type": "_stage", "stage": "decision_gap_select", "ms": round((time.perf_counter() - decision_started) * 1000)})
    schema = {s.name: s for s in state.get("question_schema", [])}
    w({"type": "question", "slot": nq.slot, "reason": nq.reason})
    t0 = time.perf_counter()
    async for chunk in llm.stream_phrase("ask", {
        "category": state["category"],
        "question_slot": nq.slot,
        "ask_hint": schema[nq.slot].ask_hint,
        "question_type": schema[nq.slot].question_type,
        "unit": schema[nq.slot].unit,
        "catalog_field": schema[nq.slot].maps_to_field,
        "candidate_count": len(state["candidates"]),
        "slots": state["slots"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "ask_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "ask"})
    history = [*state.get("conversation_history", []), {
        "role": "assistant", "content": f"Asked {nq.slot}: {schema[nq.slot].ask_hint}",
    }][-8:]
    return {
        "ask_count": state["ask_count"] + 1,
        "asked_slots": state["asked_slots"] + [nq.slot],
        "conversation_history": history,
    }


async def compare_node(state: AgentState) -> dict:
    w = get_stream_writer()
    if not state["candidates"]:
        async for chunk in llm.stream_phrase("no_match", {"slots": state["slots"], "category": state["category"]}):
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "no_match"})
        return {}
    top3 = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
    w({"type": "product_cards", "products": top3})
    w({"type": "_context", "products": top3, "slots": state["slots"]})
    t0 = time.perf_counter()
    async for chunk in llm.stream_phrase("compare", {
        "products": top3, "priorities": state["priorities"] or ["gia_re"],
    }):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "compare_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "compare"})
    history = [*state.get("conversation_history", []), {
        "role": "assistant",
        "content": "Presented shortlist: " + "; ".join(product["name"] for product in top3),
    }][-8:]
    return {"conversation_history": history}


async def detail_node(state: AgentState) -> dict:
    """Show a selected shortlist product from catalog data, never policy RAG."""
    w = get_stream_writer()
    product = state.get("explicit_product")
    if product is None:
        shortlist = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
        index = min(max(0, (state.get("selected_index") or 1) - 1), len(shortlist) - 1)
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
    history = [*state.get("conversation_history", []), {
        "role": "assistant", "content": f"Presented product details: {product['name']}",
    }][-8:]
    return {"conversation_history": history}


async def price_answer_node(state: AgentState) -> dict:
    """Answer a direct cheapest/most-expensive question within the active filter."""
    w = get_stream_writer()
    priced = [product for product in state["candidates"] if product.get("price_sale") is not None]
    if not priced:
        async for chunk in llm.stream_phrase("no_match", {"slots": state["slots"], "category": state["category"]}):
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


async def catalog_unavailable_node(state: AgentState) -> dict:
    """A catalog outage is distinct from a product request we cannot classify."""
    w = get_stream_writer()
    w({"type": "text_chunk", "content": (
        "Dạ hiện tại em chưa kết nối được danh mục sản phẩm để kiểm tra chính xác "
        "mẫu này. Anh/chị thử lại sau ít phút giúp em nhé ạ."
    )})
    w({"type": "done", "turn_type": "catalog_unavailable"})
    return {}


async def clarify_category_node(state: AgentState) -> dict:
    w = get_stream_writer()
    choices = state["category_candidates"]
    w({"type": "text_chunk", "content": (
        "Dạ anh/chị đang muốn tìm " + ", ".join(choices[:-1])
        + (" hay " if len(choices) > 1 else "") + choices[-1] + " ạ?"
    )})
    w({"type": "done", "turn_type": "clarify_category"})
    return {}


async def fulfillment_prompt_node(state: AgentState) -> dict:
    w = get_stream_writer()
    context_key = fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {}))
    w({"type": "text_chunk", "content": fulfillment.fulfillment_provider.question(context_key or "region")})
    w({"type": "done", "turn_type": "fulfillment_prompt"})
    product = state.get("explicit_product")
    if product is None and state.get("candidates"):
        shortlist = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
        index = min(max(0, (state.get("selected_index") or 1) - 1), len(shortlist) - 1)
        product = shortlist[index]
    return {"awaiting_fulfillment": True, "selected_sku": product.get("sku") if product else None}


async def fulfillment_check_node(state: AgentState) -> dict:
    w = get_stream_writer()
    product = state.get("explicit_product")
    selected_sku = state.get("selected_sku")
    if product is None and selected_sku:
        product = next((item for item in state.get("catalog_products", []) if item.get("sku") == selected_sku), None)
    if product is None:
        shortlist = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
        index = min(max(0, (state.get("selected_index") or 1) - 1), len(shortlist) - 1)
        product = shortlist[index]
    result = await fulfillment.fulfillment_provider.check(product["sku"], state["fulfillment_context"])
    w({"type": "text_chunk", "content": result.message})
    w({"type": "done", "turn_type": "fulfillment_check"})
    return {"awaiting_fulfillment": False, "selected_sku": None}


async def fulfillment_clarify_node(state: AgentState) -> dict:
    w = get_stream_writer()
    choices = state["fulfillment_candidates"]
    w({"type": "text_chunk", "content": "Dạ anh/chị muốn " + ", ".join(choices[:-1])
       + (" hay " if len(choices) > 1 else "") + choices[-1] + " ạ?"})
    w({"type": "done", "turn_type": "fulfillment_clarify"})
    return {"fulfillment_candidates": []}


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
    g.add_node("catalog_unavailable", catalog_unavailable_node)
    g.add_node("clarify_category", clarify_category_node)
    g.add_node("fulfillment_prompt", fulfillment_prompt_node)
    g.add_node("fulfillment_check", fulfillment_check_node)
    g.add_node("fulfillment_clarify", fulfillment_clarify_node)
    g.add_edge(START, "intent")
    g.add_conditional_edges("intent", route_after_intent,
                            {"retrieve": "retrieve", "policy": "policy", "off_topic": "off_topic",
                             "catalog_unavailable": "catalog_unavailable", "clarify_category": "clarify_category",
                             "fulfillment_prompt": "fulfillment_prompt", "fulfillment_check": "fulfillment_check",
                             "fulfillment_clarify": "fulfillment_clarify"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"ask": "ask", "compare": "compare", "detail": "detail", "price_answer": "price_answer",
                             "fulfillment_prompt": "fulfillment_prompt", "catalog_unavailable": "catalog_unavailable"})
    g.add_edge("ask", END)
    g.add_edge("compare", END)
    g.add_edge("detail", END)
    g.add_edge("price_answer", END)
    g.add_edge("policy", END)
    g.add_edge("off_topic", END)
    g.add_edge("catalog_unavailable", END)
    g.add_edge("clarify_category", END)
    g.add_edge("fulfillment_prompt", END)
    g.add_edge("fulfillment_check", END)
    g.add_edge("fulfillment_clarify", END)
    return g.compile(checkpointer=checkpointer)
