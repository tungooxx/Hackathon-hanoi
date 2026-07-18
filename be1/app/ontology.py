"""Runtime adapter for the exported decision ontology.

The ontology owns what can be asked and why; the chat graph only asks a
customer-owned concept when it is relevant.  Questions are read from the
Vietnamese question bank in ``data/ontology_data.json``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import NextQuestion, SlotDef


ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "data" / "ontology_data.json"

# Concept semantics, not category bindings. A question becomes available only
# when its ontology node exists for the category and its required catalog field
# is actually present. New categories therefore do not need a `_BINDINGS` edit.
_CONCEPT_RULES: dict[str, tuple[str, str, bool]] = {
    "CTX_BUDGET_MAX": ("budget_max", "price_sale", True),
    "CTX_ROOM_AREA_M2": ("area_m2", "area_max_m2", True),
    "CTX_ROOM_TYPE": ("room_type", "noise_db_min", False),
    "CTX_AFTERNOON_SUN": ("afternoon_sun", "area_max_m2", False),
    "CTX_NEED_HEATING": ("needs_heating", "loai_may", False),
    "CTX_IRON_PORTABILITY": ("iron_portable", "loai_ban_ui", False),
}


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
    """Resolve question nodes generically from ontology + current catalog."""
    questions = _questions()
    available_fields = {key for product in (products or []) for key in product}
    normalized_category = _normal(category)
    result: list[SlotDef] = []
    for concept_id, question in questions.items():
        question_category = _normal(question["category"])
        if question_category not in {"tat ca", normalized_category} or concept_id not in _CONCEPT_RULES:
            continue
        slot, field, required = _CONCEPT_RULES[concept_id]
        if products is not None and field not in available_fields:
            continue
        ask_hint = question["label"]
        result.append(SlotDef(
            name=slot,
            maps_to_field=field,
            slot_type="hard" if required else "soft",
            required=required,
            ask_hint=ask_hint,
            question_type=question.get("questionType", ""),
            possible_answers=question.get("possibleAnswers", ""),
        ))
    return result


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
