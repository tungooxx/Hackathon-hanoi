"""Utility scoring + chọn top 3 đa dạng hóa (best-fit / rẻ hơn / cao cấp hơn)."""

# priority -> (field, chiều tốt: True = càng lớn càng tốt)
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


def rank_top3(candidates: list[dict], priorities: list[str]) -> list[dict]:
    weights = {p: 1.0 / (i + 1) for i, p in enumerate(priorities)} or {"gia_re": 1.0}
    scores: dict[str, float] = {p["sku"]: 0.0 for p in candidates}
    for prio, w in weights.items():
        field, higher = _PRIORITY_FIELD[prio]
        for sku, s in _rank_score(candidates, field, higher).items():
            scores[sku] += w * s
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
