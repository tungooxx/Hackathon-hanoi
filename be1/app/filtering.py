"""Filter deterministic — 0 LLM. Hard slots loại thẳng, null policy tường minh."""
from typing import Any

from .ontology import cooling_area_required


def apply_hard_filters(products: list[dict], slots: dict[str, Any]) -> list[dict]:
    out = products
    if (budget := slots.get("budget_max")) is not None:
        out = [p for p in out if p.get("price_sale") and p["price_sale"] <= budget]
    if (budget := slots.get("budget_min")) is not None:
        out = [p for p in out if p.get("price_sale") and p["price_sale"] >= budget]
    if (area := cooling_area_required(slots)) is not None:
        # giữ sản phẩm null diện tích? Không — hard filter cần chắc chắn khớp
        out = [
            p for p in out
            if p.get("area_max_m2") and (p.get("area_min_m2") or 0) <= area <= p["area_max_m2"]
        ]
    if brand := slots.get("brand"):
        out = [p for p in out if p.get("brand", "").lower() == brand.lower()]
    if slots.get("needs_heating") is True:
        out = [p for p in out if "2 chiều" in str(p.get("loai_may", "")).lower() or "2 chieu" in str(p.get("loai_may", "")).lower()]
    if slots.get("iron_portable") is True:
        out = [p for p in out if "cầm tay" in str(p.get("loai_ban_ui", "")).lower()]
    return out
