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


def _price_options(products: list[dict]) -> list[float]:
    prices = sorted({float(p["price_sale"]) for p in products if p.get("price_sale")})
    if not prices:
        return []
    # Include the affordable edge of the observed range.  Sampling only
    # quartiles often leaves the already-cheapest default top three intact,
    # incorrectly giving the budget question zero Decision-Gap utility.
    # These are catalog values, not an invented product/category rule.
    indexes = {
        0,
        min(len(prices) - 1, 1),
        *{max(0, round((len(prices) - 1) * portion)) for portion in (0.25, 0.55, 0.8)},
    }
    return [prices[index] for index in sorted(indexes)]


def _area_options(products: list[dict]) -> list[float]:
    # Use values just inside catalog ranges, so each simulation is a realistic
    # customer answer and can reveal capacity cut-offs.
    values = sorted({float(p["area_max_m2"]) for p in products if p.get("area_max_m2")})
    return values[:5]


def _likely_answers(slot: str, products: list[dict], field: str = "") -> list[Any]:
    if field in {"price_sale", "price_original"}:
        return _price_options(products)
    if field.startswith("attributes."):
        key = field.split(".", 1)[1]
        return list({product.get("attributes", {}).get(key) for product in products if product.get("attributes", {}).get(key)})[:5]
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


def _signature(products: list[dict], priorities: list[str], catalog_preferences: list[dict] | None = None) -> list[str]:
    return [str(p["sku"]) for p in rank_top3(products, priorities, catalog_preferences)] if products else []


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
    schema: list | None = None,
    catalog_preferences: list[dict] | None = None,
) -> NextQuestion | None:
    """Select the unanswered ontology question with highest expected impact."""
    effective_schema = schema if schema is not None else ontology.get_slot_schema(category, products)
    baseline_products = apply_hard_filters(products, slots)
    baseline_products = ontology.apply_ontology_filters(
        category, baseline_products, slots, effective_schema
    )
    baseline_priorities = ontology.derive_priorities(category, slots, priorities)
    baseline = _signature(baseline_products, baseline_priorities, catalog_preferences)
    best: tuple[bool, float, str, float] | None = None

    for definition in effective_schema:
        slot = definition.name
        if slot in slots or slot in asked_slots:
            continue
        if (definition.maps_to_field in {"price_sale", "price_original"}
                and any(key in slots for key in ("budget_min", "budget_max", "budget_target"))):
            continue
        answers = _likely_answers(slot, products, definition.maps_to_field)
        if not answers:
            continue
        changes: list[float] = []
        has_empty_outcome = False
        for answer in answers:
            # Live price answers are executed through LLM-owned budget slots,
            # not by parsing a raw answer in the runtime question slot. Use
            # the same representation here or price would falsely score zero.
            simulated_slots = (
                {**slots, "budget_max": answer}
                if definition.maps_to_field in {"price_sale", "price_original"}
                else {**slots, slot: answer}
            )
            simulated_products = apply_hard_filters(products, simulated_slots)
            # Use exactly the same typed normalizer/filter executor as the
            # live conversation.  Otherwise Decision-Gap would score a
            # literal-string simulation but execute a numeric/ordinal reply.
            simulated_products = ontology.apply_ontology_filters(
                category, simulated_products, simulated_slots, effective_schema
            )
            # A clarification must refine a viable shortlist, not earn high
            # utility merely because one likely answer eliminates every
            # product. Empty-result recovery belongs to an explicit customer
            # constraint, never to Decision-Gap question selection.
            if not simulated_products:
                has_empty_outcome = True
                break
            simulated_priorities = ontology.derive_priorities(category, simulated_slots, priorities)
            changes.append(_top3_change(baseline, _signature(simulated_products, simulated_priorities, catalog_preferences)))
        if has_empty_outcome:
            continue
        expected_change = sum(changes) / len(changes)
        utility = expected_change / max(0.1, float(definition.customer_effort))
        # A question earns its place only by changing the current shortlist.
        # Ontology "required" is semantic metadata, not permission to make a
        # shopper answer a question that has zero measurable catalog effect.
        if utility > 0 and (best is None or utility > best[1]):
            best = (definition.required, utility, slot, expected_change)

    if best is None:
        return None
    _required, utility, slot, impact = best
    return NextQuestion(
        slot=slot,
        reason=(f"Decision-gap chọn '{slot}': tác động kỳ vọng lên top 3 là {impact:.2f}, "
                f"utility sau chi phí trả lời là {utility:.2f}."),
    )
