"""Deterministic Decision-Gap Clarification for the chat flow.

The ontology controls which customer questions are allowed.  This module never
uses an LLM to invent a question: it simulates each unanswered ontology slot,
measures how its likely answers change the ranked shortlist, and chooses the
largest ranking impact per unit of customer effort.
"""
from __future__ import annotations

from typing import Any

from . import ontology
from .filtering import apply_hard_filters
from .schemas import NextQuestion
from .scoring import rank_top3


_EFFORT = {"budget_max": 1.0, "area_m2": 1.0, "room_type": 1.0, "afternoon_sun": 1.0, "province": 2.0}


def _price_options(products: list[dict]) -> list[float]:
    prices = sorted({float(p["price_sale"]) for p in products if p.get("price_sale")})
    if not prices:
        return []
    indexes = {max(0, round((len(prices) - 1) * portion)) for portion in (0.25, 0.55, 0.8)}
    return [prices[index] for index in sorted(indexes)]


def _area_options(products: list[dict]) -> list[float]:
    # Use values just inside catalog ranges, so each simulation is a realistic
    # customer answer and can reveal capacity cut-offs.
    values = sorted({float(p["area_max_m2"]) for p in products if p.get("area_max_m2")})
    return values[:5]


def _likely_answers(slot: str, products: list[dict]) -> list[Any]:
    if slot == "budget_max":
        return _price_options(products)
    if slot == "area_m2":
        return _area_options(products)
    if slot == "room_type":
        return ["bedroom", "living_room", "office"]
    if slot == "afternoon_sun":
        return ["low", "high"]
    if slot == "needs_heating":
        has_heating_model = any(
            "2 chiều" in str(product.get("loai_may", "")).lower()
            or "2 chieu" in str(product.get("loai_may", "")).lower()
            for product in products
        )
        return [False, True] if has_heating_model else [False]
    if slot == "iron_portable":
        handheld = ["cầm tay" in str(product.get("loai_ban_ui", "")).lower() for product in products]
        return [False, True] if any(handheld) and not all(handheld) else [False]
    # Stock is deliberately omitted: in the current prototype it does not
    # change ranking or availability by province, so it has zero utility.
    return []


def _signature(products: list[dict], priorities: list[str]) -> list[str]:
    return [str(p["sku"]) for p in rank_top3(products, priorities)] if products else []


def _top3_change(before: list[str], after: list[str]) -> float:
    """0 = identical; 1 = entirely different. Includes membership and order."""
    if not before and not after:
        return 0.0
    union = set(before) | set(after)
    membership = 1.0 - (len(set(before) & set(after)) / len(union)) if union else 0.0
    common = set(before) & set(after)
    order = (
        sum(abs(before.index(sku) - after.index(sku)) for sku in common) / (max(1, len(before)) * 2)
        if common else 1.0
    )
    return min(1.0, 0.75 * membership + 0.25 * order)


def choose_next_question(
    category: str,
    slots: dict[str, Any],
    asked_slots: list[str],
    products: list[dict],
    priorities: list[str],
) -> NextQuestion | None:
    """Select the unanswered ontology question with highest expected impact."""
    baseline_products = apply_hard_filters(products, slots)
    baseline_priorities = ontology.derive_priorities(category, slots, priorities)
    baseline = _signature(baseline_products, baseline_priorities)
    best: tuple[float, str, float] | None = None

    for definition in ontology.get_slot_schema(category, products):
        slot = definition.name
        if slot in slots or slot in asked_slots:
            continue
        answers = _likely_answers(slot, products)
        if not answers:
            continue
        changes: list[float] = []
        for answer in answers:
            simulated_slots = {**slots, slot: answer}
            simulated_products = apply_hard_filters(products, simulated_slots)
            simulated_priorities = ontology.derive_priorities(category, simulated_slots, priorities)
            changes.append(_top3_change(baseline, _signature(simulated_products, simulated_priorities)))
        expected_change = sum(changes) / len(changes)
        utility = expected_change / _EFFORT.get(slot, 1.0)
        if utility > 0 and (best is None or utility > best[0]):
            best = (utility, slot, expected_change)

    if best is None:
        return None
    utility, slot, impact = best
    return NextQuestion(
        slot=slot,
        reason=(f"Decision-gap chọn '{slot}': tác động kỳ vọng lên top 3 là {impact:.2f}, "
                f"utility sau chi phí trả lời là {utility:.2f}."),
    )
