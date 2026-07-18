"""STUB module ontology — Tùng sẽ thay bằng module thật, GIỮ NGUYÊN 2 signature này.

Tầng 1 (slot schema) ở đây là config cứng cho máy lạnh.
Tầng 2 (suggest_next_question) ở đây chỉ chọn slot required chưa điền đầu tiên,
kèm reason đếm được từ candidates — bản thật của Tùng sẽ thay bằng information gain.
"""
from typing import Any

from .schemas import NextQuestion, SlotDef

_SCHEMAS: dict[str, list[SlotDef]] = {
    "may_lanh": [
        SlotDef(name="budget_max", maps_to_field="price_sale", slot_type="hard",
                required=True, ask_hint="hỏi ngân sách dự kiến, gợi ý các tầm giá phổ biến"),
        SlotDef(name="area_m2", maps_to_field="area_max_m2", slot_type="hard",
                required=True, ask_hint="hỏi diện tích phòng, kèm phòng có nắng chiếu trực tiếp không"),
        SlotDef(name="brand", maps_to_field="brand", slot_type="hard",
                required=False, ask_hint="chỉ hỏi nếu khách phân vân giữa các hãng"),
    ],
}


def get_slot_schema(category: str) -> list[SlotDef]:
    return _SCHEMAS.get(category, [])


def suggest_next_question(
    category: str,
    filled_slots: dict[str, Any],
    asked_slots: list[str],
    candidates: list[dict],
) -> NextQuestion | None:
    for slot_def in get_slot_schema(category):
        if not slot_def.required:
            continue
        if slot_def.name in filled_slots or slot_def.name in asked_slots:
            continue
        distinct = len({c.get(slot_def.maps_to_field) for c in candidates})
        return NextQuestion(
            slot=slot_def.name,
            reason=f"{len(candidates)} sản phẩm còn khớp có {distinct} giá trị khác nhau ở "
            f"'{slot_def.maps_to_field}' — hỏi '{slot_def.name}' để thu hẹp",
        )
    return None
