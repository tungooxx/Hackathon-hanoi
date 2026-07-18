"""Normalize untrusted catalog rows without mutating their source data.

Decision rules consume the returned canonical facts.  Failed parsing remains
``None`` so the chatbot can abstain from a fit claim instead of guessing.
"""
from __future__ import annotations

import re
from typing import Any


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("\u00a0", " ")
    if text in {"", "unknown", "null", "none", "n/a", "đang cập nhật", "hãng không công bố"}:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    return float(match.group().replace(",", ".")) if match else None


def parse_price(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "unknown", "null", "none", "n/a", "đang cập nhật"}:
        return None
    # Parse one leading monetary token only. Joining all digits turns strings
    # such as "8.990.000đ, giảm 10%" into a fabricated price.
    match = re.match(r"\s*(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(đ|vnd|tr|triệu)?\b", text)
    if not match:
        return None
    token = match.group(1)
    unit = (match.group(2) or "").lower()
    if re.search(r"(?:giảm|discount|%|trả góp|tra gop)", text[match.end():]):
        return None
    if unit in {"tr", "triệu"}:
        amount = float(token.replace(",", ".")) * 1_000_000
    elif re.search(r"[.,]\d{3}(?:[.,]\d{3})*", token):
        amount = float(re.sub(r"[.,]", "", token))
    else:
        amount = float(token.replace(",", "."))
    return int(amount) if amount > 0 else None


def parse_area_range(value: Any) -> tuple[float | None, float | None]:
    """Parse common Vietnamese room-range formats; never invent a range."""
    if value is None:
        return None, None
    text = str(value).strip().lower().replace(",", ".")
    if not text or any(marker in text for marker in ("unknown", "không công bố", "đang cập nhật")):
        return None, None
    values = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        return None, None
    if any(marker in text for marker in ("dưới", "duoi", "<")):
        return 0.0, values[0]
    if len(values) >= 2 and any(marker in text for marker in ("-", "đến", "den", "tới", "toi")):
        return min(values[0], values[1]), max(values[0], values[1])
    return None, None


def parse_noise(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).lower().replace(",", ".")
    indoor = re.search(r"dàn lạnh\s*:\s*([\d.\s/-]+)\s*db", text)
    numbers = re.findall(r"\d+(?:\.\d+)?", indoor.group(1) if indoor else text)
    return min(map(float, numbers)) if numbers else None


def parse_energy_stars(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"([1-5])\s*sao", str(value).lower())
    return int(match.group(1)) if match else None


def normalize_product(row: dict[str, Any], category: str = "may_lanh") -> dict[str, Any]:
    """Create a canonical product record plus an evidence-status map."""
    raw_range = _first(row, "area_range", "Phạm vi sử dụng", "pham_vi_su_dung")
    area_min = _number(_first(row, "area_min_m2", "area_min"))
    area_max = _number(_first(row, "area_max_m2", "area_max"))
    if area_min is None or area_max is None:
        parsed_min, parsed_max = parse_area_range(raw_range)
        area_min = area_min if area_min is not None else parsed_min
        area_max = area_max if area_max is not None else parsed_max

    sale = parse_price(_first(row, "price_sale", "sale_price", "giá khuyến mãi", "gia_khuyen_mai"))
    original = parse_price(_first(row, "price_original", "list_price", "giá gốc", "gia_goc"))
    effective_price = sale or original
    noise = _number(_first(row, "noise_db_min"))
    if noise is None:
        noise = parse_noise(_first(row, "Độ ồn", "do_on"))
    stars = _number(_first(row, "energy_stars"))
    if stars is None:
        stars = parse_energy_stars(_first(row, "Nhãn năng lượng", "nhan_nang_luong"))

    brand = str(_first(row, "brand", "Thương hiệu") or "").strip()
    result = {
        **row,
        "sku": str(_first(row, "sku", "product_id", "productidweb", "model_code") or "").strip(),
        "model_code": str(_first(row, "model_code") or "").strip(),
        "name": str(_first(row, "name", "product_name", "Tên sản phẩm") or f"Máy lạnh {brand}".strip()),
        "brand": brand,
        "category": category,
        "price_original": original,
        "price_sale": effective_price,
        "area_min_m2": area_min,
        "area_max_m2": area_max,
        "noise_db_min": noise,
        "energy_stars": int(stars) if stars is not None else None,
        "inverter": _first(row, "inverter"),
        "loai_may": _first(row, "loai_may", "Loại máy"),
        "utilities": _first(row, "utilities", "Tiện ích"),
        "_evidence": {
            "price": "VERIFIED" if effective_price is not None else "UNKNOWN",
            "area": "VERIFIED" if area_min is not None and area_max is not None else "UNKNOWN",
            "noise": "VERIFIED" if noise is not None else "UNKNOWN",
            "energy": "VERIFIED" if stars is not None else "UNKNOWN",
        },
    }
    return result


def normalize_products(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [normalize_product(row, category) for row in rows]
