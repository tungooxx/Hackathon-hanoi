"""Runtime adapter for the exported decision ontology.

The ontology owns what can be asked and why; the chat graph only asks a
customer-owned concept when it is relevant.  Questions are read from the
Vietnamese question bank in ``data/ontology_data.json``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import NextQuestion, SlotDef


ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "data" / "ontology_data.json"

def _normal(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    with ONTOLOGY_PATH.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def _questions() -> dict[str, dict[str, Any]]:
    return {item["data"]["conceptId"]: item["data"] for item in _data()["questionNodes"]}


def questions_for_category(category: str) -> list[dict[str, Any]]:
    """Return ontology-owned questions; mapping them to catalog fields is LLM-compiled."""
    normalized_category = _normal(category)
    return [
        question for question in _questions().values()
        if _normal(question["category"]) in {"tat ca", normalized_category}
    ]


def get_slot_schema(category: str, products: list[dict[str, Any]] | None = None) -> list[SlotDef]:
    """Resolve question-to-field pairs from ontology relationships + ES specs."""
    questions = _questions()
    normalized_category = _normal(category)
    attributes = sorted({key for product in (products or []) for key in product.get("attributes", {})})
    by_question: dict[str, list[str]] = {}
    for edge in _data().get("edges", []):
        relation = edge.get("data", edge)
        if relation.get("questionId"):
            by_question.setdefault(relation["questionId"], []).extend(
                value.strip() for value in relation.get("requiredFields", "").split("|") if value.strip()
            )
    result: list[SlotDef] = []
    for concept_id, question in questions.items():
        question_category = _normal(question["category"])
        if question_category not in {"tat ca", normalized_category}:
            continue
        # Generic optional prompts are not safe to transfer merely because a
        # catalog field happens to exist. They require a compiled semantic
        # mapping; reviewed Must-Have ontology questions are safe now.
        if question.get("mvpStatus") != "Must Have":
            continue
        required_fields = by_question.get(question.get("id", ""), [])
        if len(required_fields) != 1:
            continue
        field = next((actual for requested in required_fields for actual in attributes
                      if _normal(requested) == _normal(actual)), None)
        if products is not None and not field:
            continue
        result.append(SlotDef(
            name=concept_id,
            maps_to_field=f"attributes.{field}" if field else "",
            slot_type="hard" if question.get("hardGate") == "Yes" else "soft",
            required=question.get("hardGate") == "Yes",
            ask_hint=question["label"],
            question_type=question.get("questionType", ""),
            possible_answers=question.get("possibleAnswers", ""),
        ))
    return result


def _catalog_fallback_schema(category: str, products: list[dict[str, Any]]) -> list[SlotDef]:
    """Build executable, low-effort question candidates from catalog evidence.

    This is the no-mapping fallback.  It knows no product category: every
    candidate is derived from an observed field/value set, then Decision-Gap
    decides whether it can actually change the top-K before asking it.
    """
    result: list[SlotDef] = []
    prices = {product.get("price_sale") for product in products if product.get("price_sale") not in (None, 0)}
    if len(prices) >= 2:
        result.append(SlotDef(
            name="Q_FALLBACK_BUDGET",
            maps_to_field="price_sale",
            slot_type="soft",
            required=False,
            ask_hint="Ngân sách dự kiến của anh/chị khoảng bao nhiêu để em lọc các mẫu phù hợp? Nếu chưa muốn giới hạn giá, mình có thể nói không ưu tiên.",
            question_type="numeric",
            operation="max",
            unit="VND",
            customer_effort=0.2,
        ))

    # Do not expose arbitrary dirty field labels as customer questions. A raw
    # enum may affect top-K yet still be meaningless to a shopper. Such fields
    # require a validated runtime mapping (normally built/prewarmed off the
    # request path) before they become eligible to ask.
    return result


async def get_runtime_slot_schema(category: str, products: list[dict[str, Any]]) -> list[SlotDef]:
    """Return executable question candidates for the current catalog.

    A reviewed seed with only a field relationship is not executable by itself:
    it lacks the raw-value map needed to interpret a natural "có/không" reply.
    Do not block a customer turn on an LLM compiler to fill that gap.  For that
    case, use the deterministic catalog fallback and let Decision-Gap decide
    whether any candidate is worth asking. Runtime-profile compilation remains
    for categories without reviewed seed questions and should be prewarmed.
    """
    from .profile_compiler import compile_profile

    attributes = {key for product in products for key in product.get("attributes", {})}
    standard_fields = {"price_sale", "price_original"}
    available_fields = attributes | standard_fields
    if not attributes and not any(product.get("price_sale") for product in products):
        return []
    profile = await compile_profile(category, questions_for_category(category), products)
    result: list[SlotDef] = []
    for question in profile.questions:
        if question.field not in available_fields:
            continue
        question_text = question.question.strip()
        # Some structured-output providers return the ontology concept ID in
        # the question field. Resolve reviewed IDs from ontology data; reject
        # generated internal identifiers rather than exposing them to users.
        reviewed_question = _questions().get(question_text)
        if reviewed_question:
            question_text = reviewed_question["label"]
        elif re.fullmatch(r"[A-Z][A-Z0-9_]+", question_text):
            continue
        observed = {
            _normal(str(raw)) for product in products
            if (raw := product.get("attributes", {}).get(question.field)) not in (None, "")
        }
        if question.question_type == "boolean":
            boolean_values = [*question.boolean_true_values, *question.boolean_false_values]
            if (not question.boolean_true_values
                    or any(not str(raw).strip() or _normal(raw) not in observed for raw in boolean_values)):
                continue
        elif question.question_type == "choice" and (
            not question.answer_values
            or any(not str(raw).strip() for values in question.answer_values.values() for raw in values)
            or any(_normal(raw) not in observed for values in question.answer_values.values() for raw in values)
        ):
            continue
        # Slot identity is generated by the engine, never trusted from an LLM
        # token such as "mapped"/"generated". It remains stable for the same
        # category, field and question across processes.
        slot_digest = sha256(
            f"{_normal(category)}|{question.field}|{question_text}".encode("utf-8")
        ).hexdigest()[:12].upper()
        result.append(SlotDef(
            name=f"Q_RUNTIME_{slot_digest}",
            maps_to_field=(f"attributes.{question.field}" if question.field in attributes else question.field),
            slot_type="hard" if question.hard_gate else "soft",
            required=question.hard_gate,
            ask_hint=question_text,
            question_type=question.question_type,
            possible_answers=" | ".join(question.possible_answers),
            value_map=question.answer_values,
            operation=question.operation,
            ordered_values=question.ordered_values,
            unit=question.unit,
            customer_effort=question.customer_effort,
            boolean_true_values=question.boolean_true_values,
            boolean_false_values=question.boolean_false_values,
        ))
    # Do not recommend immediately merely because the ontology-to-catalog
    # compiler had no valid mapping.  Let Decision-Gap score catalog-grounded
    # fallback candidates; if none changes top-K it will still recommend.
    return result or _catalog_fallback_schema(category, products)


_GROUPED_NUMBER_RE = re.compile(r"(?<!\d)\d{1,3}(?:[.,]\d{3})+(?!\d)")
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?")
_SUPPORTED_NUMERIC_OPERATIONS = {"min", "max", "range"}
_SKIP_ANSWER = "__no_preference__"
_BOOLEAN_TRUE = "__boolean_true__"
_BOOLEAN_FALSE = "__boolean_false__"


def parse_numbers(value: Any) -> list[float]:
    """Extract numbers from dirty Vietnamese catalog or customer text."""
    text = _GROUPED_NUMBER_RE.sub(lambda match: re.sub(r"[.,]", "", match.group()), str(value))
    result: list[float] = []
    for raw in _NUMBER_RE.findall(text):
        try:
            result.append(float(raw.replace(",", ".")))
        except ValueError:
            pass
    return result


_numbers = parse_numbers


def _answer_polarity(value: Any) -> bool | None:
    """Generic language parsing, deliberately independent of product/category."""
    text = _normal(str(value))
    if not text:
        return None
    negative = ("khong", "ko", "khong can", "chua", "no", "false", "0")
    positive = ("co", "can", "dong y", "yes", "true", "1")
    if any(text == item or text.startswith(item + " ") for item in negative):
        return False
    if any(text == item or text.startswith(item + " ") for item in positive):
        return True
    return None


def _is_skip_answer(value: Any) -> bool:
    return _normal(str(value)) == _SKIP_ANSWER


def _value_constraint(definition: SlotDef, value: Any, products: list[dict]) -> tuple[str, Any] | None:
    """Compile one natural-language reply into an executable catalog predicate.

    This is intentionally generic.  The profile supplies the field operation,
    unit, enum map and ordinal ordering from catalog evidence; this function
    only parses universal language forms and never knows a category or feature.
    """
    text = _normal(str(value))
    # These are universal opt-out phrases, not category or product rules. They
    # mean the customer does not want this criterion to narrow the catalogue.
    if _is_skip_answer(value):
        return None
    field = definition.maps_to_field
    if field in {"price_sale", "price_original"}:
        numbers = _numbers(value)
        return ("max", numbers[-1]) if numbers else None
    if not field.startswith("attributes."):
        return None
    key = field.split(".", 1)[1]
    observed = sorted({str(item.get("attributes", {}).get(key, "")) for item in products
                       if item.get("attributes", {}).get(key) not in (None, "")})
    polarity = _answer_polarity(value)

    if value == _BOOLEAN_TRUE:
        return ("equals", {_normal(raw) for raw in definition.boolean_true_values}) \
            if definition.boolean_true_values else None
    if value == _BOOLEAN_FALSE:
        return ("equals", {_normal(raw) for raw in definition.boolean_false_values}) \
            if definition.boolean_false_values else None

    # Explicit profile enum mappings are the safest route for boolean/choice.
    mapped = next((raw_values for answer, raw_values in definition.value_map.items()
                   if _normal(answer) == text), None)
    if mapped is None and polarity is not None:
        mapped = next((raw_values for answer, raw_values in definition.value_map.items()
                       if _answer_polarity(answer) is polarity), None)
    if mapped is not None:
        # An explicit answer key with no raw catalog values is the profile's
        # catalog-grounded opt-out (for example, "Không ưu tiên").
        if not mapped:
            return None
        return ("equals", {_normal(raw) for raw in mapped})

    # Numeric predicates work even when every supplier formats the value
    # differently ("32 inch", "32\"", "32 in").  Infer this from catalog
    # evidence as a safety net: a compiler label must not make a natural range
    # reply become an exact-string equality filter.
    numeric_catalog = bool(observed) and sum(bool(_numbers(raw)) for raw in observed) / len(observed) >= 0.7
    if definition.question_type == "numeric" or (numeric_catalog and _numbers(value) and not definition.ordered_values):
        if definition.operation not in _SUPPORTED_NUMERIC_OPERATIONS:
            return None
        numbers = _numbers(value)
        if not numbers:
            return None
        low, high = min(numbers), max(numbers)
        operation = definition.operation
        wording = _normal(str(value))
        if any(token in wording for token in ("tren", "lon hon")):
            operation = "min_strict"
        elif any(token in wording for token in ("duoi", "nho hon")):
            operation = "max_strict"
        elif any(token in wording for token in ("tu ", "it nhat", "hoac hon")):
            operation = "min"
        elif any(token in wording for token in ("toi da", "khong qua")):
            operation = "max"
        elif len(numbers) > 1:
            operation = "range"
        return (operation, (low, high) if operation == "range" else (low if operation.startswith("min") else high))

    # Ordinal choice needs catalog-grounded ordering, never a hand-built list.
    if definition.ordered_values:
        normalized_order = [_normal(item) for item in definition.ordered_values]
        # "HD" is contained in "Full HD"; choose the most specific catalog
        # value rather than the first short substring.
        matches = sorted(
            (index for index, item in enumerate(normalized_order)
             if item and (item in text or text in item)),
            key=lambda index: len(normalized_order[index]), reverse=True,
        )
        if matches:
            index = matches[0]
            if any(token in text for token in ("hoac hon", "tro len", "cao hon", "it nhat")):
                return ("ordinal_min", set(normalized_order[index:]))
            return ("equals", {normalized_order[index]})

    # Finally allow exact/fuzzy catalog-value selection, but never turn an
    # unrelated phrase into a zero-result hard filter.
    matched = {_normal(raw) for raw in observed if _normal(raw) == text}
    return ("equals", matched) if matched else None


def answer_status(
    definition: SlotDef,
    value: Any,
    products: list[dict],
    *,
    wants_filter: bool | None = None,
    preference: str | None = None,
    skip: bool = False,
    clarify: bool = False,
    boolean_value: bool | None = None,
) -> tuple[bool, bool, str]:
    """Classify an active-question reply before it changes conversation state.

    ``resolved`` has an executable catalog predicate; ``skip`` explicitly
    means no preference; ``unresolved`` must be clarified instead of becoming
    a literal filter or silently advancing to another technical question.
    """
    if clarify:
        return False, False, "unresolved"
    if definition.question_type == "boolean" and boolean_value is not None:
        raw_values = definition.boolean_true_values if boolean_value else definition.boolean_false_values
        return (True, False, "resolved") if raw_values else (False, False, "skip")
    filter_ok = _value_constraint(definition, value, products) is not None
    preference_ok = preference in {"higher", "lower"} and ranking_supported(definition, products)
    if wants_filter is False:
        filter_ok = False
    if wants_filter is True and not filter_ok:
        if not preference_ok:
            return False, False, "unresolved"
    if filter_ok or preference_ok:
        return filter_ok, preference_ok, "resolved"
    if skip or _is_skip_answer(value):
        return False, False, "skip"
    return False, False, "unresolved"


def ranking_supported(definition: SlotDef, products: list[dict]) -> bool:
    """Verify a generic higher/lower preference against catalog evidence."""
    if definition.ordered_values:
        return True
    if definition.maps_to_field in {"price_sale", "price_original"}:
        return True
    if not definition.maps_to_field.startswith("attributes."):
        return False
    field = definition.maps_to_field.split(".", 1)[1]
    values = [item.get("attributes", {}).get(field) for item in products]
    present = [value for value in values if value not in (None, "")]
    return bool(present) and sum(bool(_numbers(value)) for value in present) / len(present) >= 0.7


def apply_ontology_filters(category: str, products: list[dict], slots: dict[str, Any],
                           schema: list[SlotDef] | None = None) -> list[dict]:
    """Apply answered ontology concepts using their relationship-resolved ES field."""
    out = products
    for definition in schema if schema is not None else get_slot_schema(category, products):
        value = slots.get(definition.name)
        if value is None:
            continue
        if (definition.question_type == "numeric"
                and definition.operation not in _SUPPORTED_NUMERIC_OPERATIONS):
            raise ValueError(f"Unsupported numeric operation: {definition.operation}")
        constraint = _value_constraint(definition, value, out)
        if constraint is None:
            continue
        operation, expected = constraint
        if definition.maps_to_field in {"price_sale", "price_original"}:
            out = [item for item in out if item.get(definition.maps_to_field) is not None
                   and float(item[definition.maps_to_field]) <= float(expected)]
            continue
        if not definition.maps_to_field.startswith("attributes."):
            continue
        field = definition.maps_to_field.split(".", 1)[1]
        if operation in {"equals", "ordinal_min"}:
            out = [item for item in out if _normal(str(item.get("attributes", {}).get(field, ""))) in expected]
        elif operation in {"min", "max", "min_strict", "max_strict", "range"}:
            def matches_number(item: dict) -> bool:
                values = _numbers(item.get("attributes", {}).get(field, ""))
                if not values:
                    return False
                if operation == "min":
                    return max(values) >= float(expected)
                if operation == "min_strict":
                    return max(values) > float(expected)
                if operation == "max":
                    return min(values) <= float(expected)
                if operation == "max_strict":
                    return min(values) < float(expected)
                low, high = expected
                return any(low <= number <= high for number in values)
            out = [item for item in out if matches_number(item)]
    return out


def suggest_next_question(
    category: str,
    filled_slots: dict[str, Any],
    asked_slots: list[str],
    candidates: list[dict],
) -> NextQuestion | None:
    """Ask one relevant user concept; never ask a technical product attribute."""
    for slot in get_slot_schema(category, candidates):
        if slot.name in filled_slots or slot.name in asked_slots:
            continue
        verified_values = {p.get(slot.maps_to_field) for p in candidates if p.get(slot.maps_to_field) is not None}
        if not slot.required and len(verified_values) < 2:
            continue
        purpose = "cần để chọn máy vừa với phòng" if slot.required else "có thể giúp xếp hạng sát nhu cầu hơn"
        return NextQuestion(
            slot=slot.name,
            reason=f"Ontology chọn '{slot.name}': {purpose}; câu hỏi lấy từ question bank tiếng Việt.",
        )
    return None


def cooling_area_required(slots: dict[str, Any]) -> float | None:
    """RULE-AC-003: strong afternoon sun needs a conservative capacity margin."""
    area = slots.get("area_m2")
    if area is None:
        return None
    return float(area) * (1.2 if slots.get("afternoon_sun") == "high" else 1.0)


def derive_priorities(category: str, slots: dict[str, Any], priorities: list[str]) -> list[str]:
    result = list(priorities)
    category_slug = "_".join(_normal(category).split())
    if category_slug == "may_lanh" and slots.get("room_type") == "bedroom" and "it_on" not in result:
        result.append("it_on")
    return result
