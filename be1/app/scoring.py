"""Utility scoring + chọn top 3 đa dạng hóa (best-fit / rẻ hơn / cao cấp hơn)."""

# priority -> (field, chiều tốt: True = càng lớn càng tốt)
from .ontology import parse_numbers

_PRIORITY_FIELD = {
    "tiet_kiem_dien": ("energy_stars", True),
    "it_on": ("noise_db_min", False),
    "gia_re": ("price_sale", False),
}


def _rank_score(products: list[dict], field: str, higher_better: bool) -> dict[str, float]:
    """Điểm 0..1 theo rank; sản phẩm null field nhận 0 (không được thưởng vì thiếu data)."""
    have = [p for p in products if p.get(field) is not None]
    have.sort(key=lambda p: p[field], reverse=higher_better)
    n = len(have)
    return {p["sku"]: (n - i) / n for i, p in enumerate(have)}


def _catalog_preference_score(products: list[dict], field: str, higher_better: bool) -> dict[str, float]:
    """Rank an evidenced numeric catalog field without category-specific code."""
    pairs: list[tuple[dict, float]] = []
    if field.startswith("attributes."):
        key = field.split(".", 1)[1]
        for product in products:
            tokens = parse_numbers(product.get("attributes", {}).get(key, ""))
            if tokens:
                pairs.append((product, max(tokens)))
    else:
        for product in products:
            if product.get(field) is not None:
                pairs.append((product, float(product[field])))
    pairs.sort(key=lambda item: item[1], reverse=higher_better)
    return {product["sku"]: (len(pairs) - index) / len(pairs) for index, (product, _value) in enumerate(pairs)} if pairs else {}


def rank_top3(candidates: list[dict], priorities: list[str], catalog_preferences: list[dict] | None = None) -> list[dict]:
    weights = {p: 1.0 / (i + 1) for i, p in enumerate(priorities)}
    explicit_price_preference = any(
        preference.get("field") in {"price_sale", "price_original"}
        for preference in catalog_preferences or []
    )
    if not weights and not explicit_price_preference:
        weights = {"gia_re": 1.0}
    # A missing price cannot support a price-based recommendation. Keep it for
    # non-price decisions, but never show it as a "cheap" option when priced
    # alternatives exist.
    if "gia_re" in weights and any(product.get("price_sale") is not None for product in candidates):
        candidates = [product for product in candidates if product.get("price_sale") is not None]
    scores: dict[str, float] = {p["sku"]: 0.0 for p in candidates}
    for prio, w in weights.items():
        field, higher = _PRIORITY_FIELD[prio]
        for sku, s in _rank_score(candidates, field, higher).items():
            scores[sku] += w * s
    for preference in catalog_preferences or []:
        for sku, score in _catalog_preference_score(
            candidates, preference.get("field", ""), preference.get("direction") == "higher"
        ).items():
            scores[sku] += score
    ranked = sorted(candidates, key=lambda p: scores[p["sku"]], reverse=True)

    best = ranked[0]
    pool = ranked[1:6]
    cheaper = min(pool, key=lambda p: p.get("price_sale") or 1e12, default=None)
    premium = max(
        [p for p in pool if p is not cheaper],
        key=lambda p: p.get("price_sale") or 0, default=None,
    )
    top = [best] + [p for p in (cheaper, premium) if p]
    # bù cho đủ 3 nếu trùng/thiếu
    for p in ranked:
        if len(top) >= 3:
            break
        if p not in top:
            top.append(p)
    return top[:3]
