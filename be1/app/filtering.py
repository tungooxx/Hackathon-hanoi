"""Filter deterministic — 0 LLM. Hard slots loại thẳng, null policy tường minh."""
from typing import Any


def apply_hard_filters(products: list[dict], slots: dict[str, Any]) -> list[dict]:
    out = products
    if budget := slots.get("budget_max"):
        out = [p for p in out if p.get("price_sale") and p["price_sale"] <= budget]
    if area := slots.get("area_m2"):
        # giữ sản phẩm null diện tích? Không — hard filter cần chắc chắn khớp
        out = [
            p for p in out
            if p.get("area_max_m2") and (p.get("area_min_m2") or 0) <= area <= p["area_max_m2"]
        ]
    if brand := slots.get("brand"):
        out = [p for p in out if p.get("brand", "").lower() == brand.lower()]
    return out
