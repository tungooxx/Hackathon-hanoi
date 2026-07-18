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

from . import fulfillment, llm, ontology, product_repo, rag, tools
from .config import COMPARE_THRESHOLD, LLM_API_KEY, MOCK_LLM, RAG_MIN_SCORE, RAG_TOP_K
from .decision_gap import choose_next_question
from .filtering import apply_hard_filters
from .schemas import SlotDef
from .scoring import rank_top3
from .session_history import (
    HistoryMessage,
    append_message,
    render_session_context,
)


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
    product_mentions: list[str]
    unknown_products: list[str]
    web_spec: dict[str, Any]
    enrich_pending: bool
    found_in_catalog: bool
    catalog_lookup_failed: bool
    explicit_product: dict[str, Any] | None
    question_schema: list[Any]
    category_candidates: list[str]
    fulfillment_context: dict[str, str]
    awaiting_fulfillment: bool
    fulfillment_for_shortlist: bool
    fulfillment_resume_comparison: bool
    fulfillment_candidates: list[str]
    catalog_preferences: list[dict[str, str]]
    # Session-history agent: cumulative compressed Markdown + uncompressed tail.
    session_content: str
    recent_messages: list[HistoryMessage]
    topic_changed: bool


def _slot_defs(raw: list[Any] | None) -> list[SlotDef]:
    """question_schema đi qua checkpointer Postgres bị deserialize thành dict thuần —
    dựng lại SlotDef để mọi nơi dùng attribute access không sập ở turn sau."""
    return [item if isinstance(item, SlotDef) else SlotDef.model_validate(item) for item in (raw or [])]


def _customer_visible_slots(slots: dict[str, Any], schema: list[Any] | None = None) -> dict[str, Any]:
    """Never expose runtime IDs or executor sentinels in the UI funnel."""
    visible = {
        key: value for key, value in slots.items()
        # Question IDs are executor state, not customer-facing filters.  This
        # covers both LLM-compiled and catalog-fallback IDs.
        if (not key.startswith("Q_")
            and key not in {"price_sale", "price_original"}
            and value != ontology._SKIP_ANSWER)
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
    catalog_preferences = list(state.get("catalog_preferences", []))
    category = state.get("category")
    expected_question = None
    expected_definition = None
    if category and asked:
        schema = {definition.name: definition for definition in (
            _slot_defs(state.get("question_schema")) or ontology.get_slot_schema(category)
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
    try:
        known_categories = await product_repo.list_categories()
    except Exception:
        known_categories = []
    result = await llm.extract_intent(
        state["user_input"], state.get("category"), state.get("slots", {}),
        expected_question=expected_question,
        session_content=state.get("session_content", ""),
        recent_messages=state.get("recent_messages", []),
        known_categories=known_categories,
    )
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
        # A reply to an active question is data for that question, not fresh
        # category-search input.  Fuzzy discovery can otherwise turn ordinary
        # answers such as "áo sơ mi công sở" into an unrelated catalog
        # category. The intent prompt explicitly marks a real topic switch via
        # active_question_override, which is the only case allowed to resolve.
        resolved_category, category_candidates = await product_repo.resolve_category_candidates(state["user_input"])
        explicit_category_label = bool(
            resolved_category
            and product_repo._contains_label(
                product_repo._normal(state["user_input"]),
                product_repo._normal(resolved_category),
            )
        )
        if expected_question and not result.active_question_override and not explicit_category_label:
            resolved_category, category_candidates = None, []
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

    topic_changed = bool(
        category
        and result.intent_type == "new_topic"
        and result.category
        and result.category != category
    )
    if topic_changed:
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
        "product_mentions": result.product_mentions,
        "catalog_lookup_failed": catalog_lookup_failed,
        "category_candidates": category_candidates,
        "fulfillment_context": fulfillment_context,
        "awaiting_fulfillment": awaiting_fulfillment,
        "fulfillment_candidates": fulfillment_candidates,
        "catalog_preferences": catalog_preferences,
        "topic_changed": topic_changed,
    }


async def history_control_node(state: AgentState) -> dict:
    """Compress completed older turns when intent detects a topic change."""

    w = get_stream_writer()
    session_content = state.get("session_content", "")
    recent_messages = list(state.get("recent_messages", []))

    if state.get("topic_changed") and recent_messages:
        t0 = time.perf_counter()
        session_content = await llm.summarize_session_history(
            session_content,
            recent_messages,
        )
        recent_messages = []
        w({
            "type": "_stage",
            "stage": "history_compress",
            "ms": round((time.perf_counter() - t0) * 1000),
        })
        # The authenticated router persists this owner-scoped Markdown in the
        # chat_sessions row. It remains internal and is never forwarded by SSE.
        w({
            "type": "_session_content_update",
            "content": session_content,
        })

    recent_messages = append_message(
        recent_messages,
        role="user",
        content=state["user_input"],
    )
    return {
        "session_content": session_content,
        "recent_messages": recent_messages,
    }


def _phrase_context(state: AgentState, context: dict[str, Any]) -> dict[str, Any]:
    history_context = render_session_context(
        state.get("session_content", ""),
        state.get("recent_messages", []),
    )
    return {
        **context,
        "history_context": history_context,
    }


def _assistant_history(state: AgentState, content: str) -> dict:
    return {
        "recent_messages": append_message(
            state.get("recent_messages", []),
            role="assistant",
            content=content,
        )
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
       "filters": _customer_visible_slots(state["slots"], question_schema), "category": state["category"]})
    return {
        "candidates": candidates, "catalog_products": products, "total_in_category": len(products),
        "explicit_product": explicit_product, "question_schema": question_schema,
        "catalog_lookup_failed": False,
    }


def route_after_intent(state: AgentState) -> str:
    user_input = state.get("user_input", "")
    # A pure greeting contains no shopping intent.  It must win over a category
    # hallucinated by the intent model, otherwise "chào" can enter retrieval
    # for an unrelated catalog category.
    if llm.looks_like_greeting(user_input):
        return "greeting"
    # Khách đang trả lời câu hỏi nhu cầu của luồng "sản phẩm lạ" -> tiếp tục resolve.
    if state.get("enrich_pending"):
        return "resolve"
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
    # Lưới an toàn tất định: một từ khoá dịch vụ/chính sách rõ ràng (bảo hành, đổi trả,
    # giao hàng...) là câu hỏi CSKH, KHÔNG phải tra kho — kể cả khi model intent nhỏ đọc
    # nhầm 'bảo hành ip8' thành product_mentions. Đặt SAU gate selected_index/
    # wants_product_details ở trên nên 'bảo hành mẫu vừa chọn' vẫn ra chi tiết SP, không
    # bị nhánh 'sản phẩm lạ' cướp thành câu 'nới lỏng bộ lọc' vô nghĩa.
    if llm.looks_like_policy(user_input):
        return "policy"
    if state.get("category_candidates"):
        return "clarify_category"
    if state.get("catalog_lookup_failed"):
        return "catalog_unavailable"
    # Only use the expensive name/model lookup when the category is still
    # unknown.  A generic category phrase can be returned in product_mentions
    # by an LLM ("bàn ủi", "tivi"); sending it to search_catalog returns a
    # broad hit list and bypasses retrieve + Decision-Gap incorrectly.  Once a
    # category is resolved, retrieve_node already finds an exact named model
    # within that category via product_repo.find_named_product().
    if state.get("product_mentions") and not state.get("category"):
        return "product_lookup"
    # Chào hỏi thuần (chưa nêu nhu cầu) phải được đón tiếp + hỏi ngược, KHÔNG rơi vào
    # off_topic 'chưa hỗ trợ được'. Đặt trước off_topic để thắng khi intent lỡ xếp off_topic.
    if state["intent_type"] == "off_topic":
        return "off_topic"
    if not state.get("category"):
        return "off_topic"  # chưa biết khách muốn loại gì và câu nói không có tín hiệu
    return "retrieve"


def route_after_product_lookup(state: AgentState) -> str:
    return "compare" if state.get("found_in_catalog") else "enrich"


def route_after_retrieve(state: AgentState) -> str:
    if state.get("catalog_lookup_failed"):
        return "catalog_unavailable"
    if not state["candidates"]:
        return "compare"  # compare_node xử lý case rỗng (no_match)
    if state.get("explicit_product") or state.get("selected_index") or state.get("wants_product_details"):
        # Chỉ hỏi tỉnh/thành khi khách THẬT SỰ chốt một mẫu cụ thể; câu hỏi thông số
        # ("tốn điện không", "tản nhiệt sao") phải được trả lời thẳng, không bị chặn.
        if (state.get("explicit_product") or state.get("selected_index")) and \
                fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
            return "fulfillment_prompt"
        return "detail"
    if state.get("price_order"):
        return "price_answer"
    # A shortlist that already fits on the comparison surface is actionable.
    # Do not make the shopper answer another preference merely because it can
    # reshuffle those same few products; show their trade-offs instead.
    if len(state["candidates"]) <= COMPARE_THRESHOLD:
        if fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
            return "fulfillment_prompt"
        return "compare"
    if state["intent_type"] == "force_answer":
        if fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
            return "fulfillment_prompt"
        return "compare"
    started = time.perf_counter()
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"],
        _slot_defs(state.get("question_schema")) or None, state.get("catalog_preferences"),
    )
    get_stream_writer()({"type": "_stage", "stage": "decision_gap", "ms": round((time.perf_counter() - started) * 1000)})
    if nq:
        return "ask"
    if fulfillment.fulfillment_provider.required_context(state.get("fulfillment_context", {})):
        return "fulfillment_prompt"
    return "compare"


async def ask_node(state: AgentState) -> dict:
    w = get_stream_writer()
    decision_started = time.perf_counter()
    question_schema = _slot_defs(state.get("question_schema"))
    nq = choose_next_question(
        state["category"], state["slots"], state["asked_slots"], state["catalog_products"], state["priorities"],
        question_schema or None, state.get("catalog_preferences"),
    )
    w({"type": "_stage", "stage": "decision_gap_select", "ms": round((time.perf_counter() - decision_started) * 1000)})
    schema = {s.name: s for s in question_schema}
    w({"type": "question", "slot": nq.slot, "reason": nq.reason})
    t0 = time.perf_counter()
    chunks: list[str] = []
    definition = schema[nq.slot]
    if nq.slot.startswith("Q_FALLBACK_"):
        # This path is intentionally data-derived and already has a safe,
        # customer-facing question. Avoid another LLM round-trip that can turn
        # one fallback question into several speculative technical questions.
        chunks.append(definition.ask_hint)
        w({"type": "text_chunk", "content": definition.ask_hint})
    else:
        async for chunk in llm.stream_phrase("ask", _phrase_context(state, {
            "category": state["category"],
            "question_slot": nq.slot,
            "ask_hint": definition.ask_hint,
            "question_type": definition.question_type,
            "unit": definition.unit,
            "catalog_field": definition.maps_to_field,
            "candidate_count": len(state["candidates"]),
            "slots": state["slots"],
        })):
            chunks.append(chunk)
            w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "ask_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "ask"})
    return {
        "ask_count": state["ask_count"] + 1,
        "asked_slots": state["asked_slots"] + [nq.slot],
        **_assistant_history(state, "".join(chunks)),
    }


async def compare_node(state: AgentState) -> dict:
    w = get_stream_writer()
    if not state["candidates"]:
        chunks: list[str] = []
        async for chunk in llm.stream_phrase(
            "no_match",
            _phrase_context(state, {"slots": state["slots"], "category": state["category"]}),
        ):
            chunks.append(chunk)
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "no_match"})
        return _assistant_history(state, "".join(chunks))
    top3 = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
    w({"type": "product_cards", "products": top3})
    w({"type": "_context", "products": top3, "slots": state["slots"]})
    t0 = time.perf_counter()
    chunks = []
    async for chunk in llm.stream_phrase("compare", _phrase_context(state, {
        "products": top3, "priorities": state["priorities"] or ["gia_re"],
    })):
        chunks.append(chunk)
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "compare_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "compare"})
    return _assistant_history(state, "".join(chunks))


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
    chunks: list[str] = []
    async for chunk in llm.stream_phrase("detail", _phrase_context(state, {
        "product": product,
        "question": state["user_input"],
    })):
        chunks.append(chunk)
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "detail_phrase", "ms": round((time.perf_counter() - t0) * 1000)})
    w({"type": "done", "turn_type": "detail"})
    return _assistant_history(state, "".join(chunks))


async def price_answer_node(state: AgentState) -> dict:
    """Answer a direct cheapest/most-expensive question within the active filter."""
    w = get_stream_writer()
    priced = [product for product in state["candidates"] if product.get("price_sale") is not None]
    if not priced:
        chunks: list[str] = []
        async for chunk in llm.stream_phrase(
            "no_match",
            _phrase_context(state, {"slots": state["slots"], "category": state["category"]}),
        ):
            chunks.append(chunk)
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "price_answer"})
        return _assistant_history(state, "".join(chunks))
    product = (
        max(priced, key=lambda item: item["price_sale"])
        if state["price_order"] == "highest"
        else min(priced, key=lambda item: item["price_sale"])
    )
    w({"type": "product_cards", "products": [product]})
    chunks = []
    async for chunk in llm.stream_phrase("price_answer", _phrase_context(state, {
        "product": product,
        "price_order": state["price_order"],
    })):
        chunks.append(chunk)
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "price_answer"})
    return _assistant_history(state, "".join(chunks))


async def policy_node(state: AgentState) -> dict:
    """RAG: tìm chunk chính sách liên quan -> trả lời grounded. Điểm thấp -> thú nhận không có."""
    w = get_stream_writer()
    t0 = time.perf_counter()
    hits = await rag.search(state["user_input"], RAG_TOP_K)
    w({"type": "_stage", "stage": "policy_retrieve", "ms": round((time.perf_counter() - t0) * 1000)})

    if not hits or hits[0].score < RAG_MIN_SCORE:
        w({"type": "_policy_miss", "top_score": hits[0].score if hits else 0.0})
        chunks: list[str] = []
        async for chunk in llm.stream_phrase(
            "policy_no_info",
            _phrase_context(state, {}),
        ):
            chunks.append(chunk)
            w({"type": "text_chunk", "content": chunk})
        w({"type": "done", "turn_type": "policy"})
        return _assistant_history(state, "".join(chunks))

    hit_dicts = [{"title": h.title, "source": h.source, "text": h.text, "score": h.score} for h in hits]
    w({"type": "policy_sources",
       "sources": [{"title": h.title, "source": h.source, "score": h.score} for h in hits]})
    w({"type": "_context", "policy_hits": hit_dicts, "query": state["user_input"]})
    t1 = time.perf_counter()
    chunks = []
    async for chunk in llm.stream_phrase(
        "policy",
        _phrase_context(
            state,
            {"question": state["user_input"], "hits": hit_dicts},
        ),
    ):
        chunks.append(chunk)
        w({"type": "text_chunk", "content": chunk})
    w({"type": "_stage", "stage": "policy_phrase", "ms": round((time.perf_counter() - t1) * 1000)})
    w({"type": "done", "turn_type": "policy"})
    return _assistant_history(state, "".join(chunks))


async def greeting_node(state: AgentState) -> dict:
    # Chào hỏi thuần: đón tiếp + hỏi ngược nhu cầu. Coi là 'ask' (đang gợi mở nhu cầu),
    # KHÔNG phải off_topic — tránh giọng 'chưa hỗ trợ được' cho một câu chào.
    w = get_stream_writer()
    async for chunk in llm.stream_phrase("greeting", {}):
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "ask"})
    return {}


async def off_topic_node(state: AgentState) -> dict:
    w = get_stream_writer()
    chunks: list[str] = []
    async for chunk in llm.stream_phrase(
        "off_topic",
        _phrase_context(state, {}),
    ):
        chunks.append(chunk)
        w({"type": "text_chunk", "content": chunk})
    w({"type": "done", "turn_type": "off_topic"})
    return _assistant_history(state, "".join(chunks))


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
    shortlist_request = product is None and not state.get("selected_index")
    if product is None and state.get("candidates"):
        shortlist = rank_top3(state["candidates"], state["priorities"], state.get("catalog_preferences"))
        index = min(max(0, (state.get("selected_index") or 1) - 1), len(shortlist) - 1)
        product = shortlist[index]
    return {
        "awaiting_fulfillment": True,
        "fulfillment_for_shortlist": shortlist_request,
        "selected_sku": product.get("sku") if product else None,
    }


async def fulfillment_check_node(state: AgentState) -> dict:
    w = get_stream_writer()
    if state.get("fulfillment_for_shortlist"):
        region = state["fulfillment_context"]["region"]
        w({"type": "text_chunk", "content": (
            f"Dạ các mẫu đang phù hợp đều có thể giao tại {region} ạ. "
            "Em gửi anh/chị các lựa chọn để mình so sánh nhé."
        )})
        return {
            "awaiting_fulfillment": False,
            "fulfillment_for_shortlist": False,
            "fulfillment_resume_comparison": True,
            "selected_sku": None,
        }
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
    return {
        "awaiting_fulfillment": False,
        "fulfillment_for_shortlist": False,
        "fulfillment_resume_comparison": False,
        "selected_sku": None,
    }


def route_after_fulfillment_check(state: AgentState) -> str:
    """Only a shortlist availability check continues into a recommendation."""
    return "compare" if state.get("fulfillment_resume_comparison") else "end"


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
    g.add_node("history_control", history_control_node)
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
    g.add_node("greeting", greeting_node)
    g.add_node("catalog_unavailable", catalog_unavailable_node)
    g.add_node("clarify_category", clarify_category_node)
    g.add_node("fulfillment_prompt", fulfillment_prompt_node)
    g.add_node("fulfillment_check", fulfillment_check_node)
    g.add_node("fulfillment_clarify", fulfillment_clarify_node)
    g.add_edge(START, "intent")
    g.add_edge("intent", "history_control")
    g.add_conditional_edges("history_control", route_after_intent,
                            {"retrieve": "retrieve", "policy": "policy", "off_topic": "off_topic",
                             "greeting": "greeting", "product_lookup": "product_lookup", "resolve": "resolve",
                             "catalog_unavailable": "catalog_unavailable", "clarify_category": "clarify_category",
                             "fulfillment_prompt": "fulfillment_prompt", "fulfillment_check": "fulfillment_check",
                             "fulfillment_clarify": "fulfillment_clarify"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"ask": "ask", "compare": "compare", "detail": "detail", "price_answer": "price_answer",
                             "fulfillment_prompt": "fulfillment_prompt", "catalog_unavailable": "catalog_unavailable"})
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
    g.add_edge("greeting", END)
    g.add_edge("catalog_unavailable", END)
    g.add_edge("clarify_category", END)
    g.add_edge("fulfillment_prompt", END)
    g.add_conditional_edges(
        "fulfillment_check",
        route_after_fulfillment_check,
        {"compare": "compare", "end": END},
    )
    g.add_edge("fulfillment_clarify", END)
    return g.compile(checkpointer=checkpointer)
