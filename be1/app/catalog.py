"""Public catalog browsing — trả về TẤT CẢ sản phẩm khớp bộ lọc của một funnel chat.

Chat chỉ stream top-3 thẻ sản phẩm. Khi khách bấm vào "Còn N/M mẫu khớp",
FE gọi endpoint này với đúng category + slots của funnel đó để render danh sách
đầy đủ (kèm phân trang) trong UI chính. Deterministic, 0 LLM — dùng lại
get_products + apply_hard_filters y hệt nhánh retrieve của graph.
"""
from typing import Any

from fastapi import APIRouter, Query

from . import product_repo
from .filtering import apply_hard_filters

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("/products")
async def list_products(
    category: str = Query(..., description="Tên category (khớp category_name.raw)"),
    budget_max: float | None = Query(default=None),
    area_m2: float | None = Query(default=None),
    afternoon_sun: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    needs_heating: bool | None = Query(default=None),
    iron_portable: bool | None = Query(default=None),
) -> dict[str, Any]:
    """Danh sách sản phẩm của `category` sau khi áp bộ lọc cứng của funnel.

    Trả toàn bộ danh sách khớp (FE tự phân trang) + count/total để hiển thị header.
    """
    products = await product_repo.get_products(category)
    slots: dict[str, Any] = {
        "budget_max": budget_max,
        "area_m2": area_m2,
        "afternoon_sun": afternoon_sun,
        "brand": brand,
        "needs_heating": needs_heating,
        "iron_portable": iron_portable,
    }
    slots = {k: v for k, v in slots.items() if v is not None}
    matched = apply_hard_filters(products, slots)
    return {
        "category": category,
        "count": len(matched),
        "total": len(products),
        "products": matched,
    }
