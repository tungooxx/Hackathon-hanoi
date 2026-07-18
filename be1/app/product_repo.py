"""Nguồn dữ liệu sản phẩm = Elasticsearch (index products, shape thô crawler).

Gộp về 1 BE: bỏ BE2/fixtures. retrieve_node -> get_products(category) query thẳng ES,
rồi normalize doc thô (product_name, sale_price, specs[{key,value}]) sang shape chuẩn
mà filtering.py / scoring.py / phrasing LLM cần (sku, price_sale, area_*_m2, noise_db_min,
energy_stars, inverter, brand, ...).
"""
import re
import unicodedata
from typing import Any

from db.elasticsearch import elasticsearch

# chỉ lấy field cần cho normalize -> bỏ search_text/promotion/... (payload nhẹ hơn nhiều)
_SOURCE = [
    "product_id", "product_code", "product_name", "brand",
    "original_price", "sale_price", "specs", "warranty_policy",
]

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _normal(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


async def resolve_category(query_text: str) -> str | None:
    """Discover a real category directly from Elasticsearch index values."""
    response = await elasticsearch.search({
        "size": 0,
        "aggs": {"categories": {"terms": {"field": "category_name.raw", "size": 1000}}},
    })
    query = _normal(query_text)
    categories = [bucket["key"] for bucket in response.get("aggregations", {}).get("categories", {}).get("buckets", [])]
    matches = [category for category in categories if _normal(category) in query]
    return max(matches, key=lambda item: len(_normal(item))) if matches else None


def _f(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _spec_map(specs: list[dict]) -> dict[str, str]:
    return {(s.get("key") or "").strip(): (s.get("value") or "").strip() for s in specs or []}


def _spec_find(specs: dict[str, str], *substrings: str) -> str | None:
    """Trả value của spec đầu tiên có key chứa 1 trong các substring (khớp không dấu-hoa-thường)."""
    for key, val in specs.items():
        low = key.lower()
        if any(sub in low for sub in substrings):
            return val
    return None


def _parse_area(specs: dict[str, str], name: str) -> tuple[float | None, float | None]:
    """area_min/max (m²) từ spec 'Phạm vi làm lạnh' hoặc tên SP '(phòng 30-40m²)'."""
    text = _spec_find(specs, "phạm vi làm lạnh", "diện tích") or ""
    src = text or name
    # 'dưới 15m2' -> (0, 15)
    if m := re.search(r"dưới\s*(\d+)\s*m", src, re.I):
        return 0.0, float(m.group(1))
    # 'trên 60m2' -> (60, None)
    if m := re.search(r"trên\s*(\d+)\s*m", src, re.I):
        return float(m.group(1)), None
    # '30 - 40m2' -> (30, 40)
    if m := re.search(r"(\d+)\s*[-–]\s*(\d+)\s*m", src):
        return float(m.group(1)), float(m.group(2))
    return None, None


def _parse_noise_min(specs: dict[str, str]) -> float | None:
    """Độ ồn thấp nhất của DÀN LẠNH, vd 'Dàn lạnh: 16/14/12 dB - Dàn nóng: 57 dB' -> 12."""
    text = _spec_find(specs, "độ ồn", "ồn")
    if not text:
        return None
    indoor = re.split(r"dàn\s*nóng", text, flags=re.I)[0]  # bỏ phần dàn nóng
    nums = [float(x) for x in _NUM.findall(indoor)]
    return min(nums) if nums else None


def _parse_energy_stars(specs: dict[str, str]) -> int | None:
    text = _spec_find(specs, "hiệu suất năng lượng", "bậc năng lượng", "số sao", "energy")
    if not text:
        return None
    m = _NUM.search(text)
    return int(float(m.group())) if m else None


def _parse_inverter(specs: dict[str, str], name: str) -> bool:
    val = _spec_find(specs, "inverter")
    if val is not None:
        return "có" in val.lower() or "inverter" in val.lower()
    return "inverter" in name.lower()


def _normalize(src: dict, category: str) -> dict:
    specs = _spec_map(src.get("specs", []))
    name = src.get("product_name", "")
    area_min, area_max = _parse_area(specs, name)
    return {
        "sku": src.get("product_code") or str(src.get("product_id", "")),
        "model_code": str(src.get("product_id", "")),
        "name": name,
        "brand": src.get("brand", ""),
        "category": category,
        "price_original": _f(src.get("original_price")),
        "price_sale": _f(src.get("sale_price")),
        "area_min_m2": area_min,
        "area_max_m2": area_max,
        "noise_db_min": _parse_noise_min(specs),
        "inverter": _parse_inverter(specs, name),
        "energy_stars": _parse_energy_stars(specs),
        "loai_may": _spec_find(specs, "loại máy"),
        "warranty_parts": _spec_find(specs, "bảo hành cục", "bảo hành linh kiện", "bảo hành sản phẩm")
        or src.get("warranty_policy"),
        "utilities": _spec_find(specs, "tiện ích"),
    }


async def get_products(category: str) -> list[dict]:
    body = {
        "size": 500,
        "_source": _SOURCE,
        "query": {"term": {"category_name.raw": category}},
    }
    resp = await elasticsearch.search(body)
    hits = resp.get("hits", {}).get("hits", [])
    return [_normalize(h.get("_source", {}), category) for h in hits]
