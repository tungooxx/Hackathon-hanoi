"""Nguồn dữ liệu sản phẩm = Elasticsearch (index products, shape thô crawler).

Gộp về 1 BE: bỏ BE2/fixtures. retrieve_node -> get_products(category) query thẳng ES,
rồi normalize doc thô (product_name, sale_price, specs[{key,value}]) sang shape chuẩn
mà filtering.py / scoring.py / phrasing LLM cần (sku, price_sale, area_*_m2, noise_db_min,
energy_stars, inverter, brand, ...).
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from db.elasticsearch import elasticsearch

# chỉ lấy field cần cho normalize -> bỏ search_text/promotion/... (payload nhẹ hơn nhiều)
_SOURCE = [
    "product_id", "product_code", "product_name", "brand", "category_name",
    "original_price", "sale_price", "specs", "warranty_policy",
    "image_url", "url",
]

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _normal(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _is_subsequence(abbreviation: str, label: str) -> bool:
    """Whether an abbreviation's letters occur in order in a category label."""
    iterator = iter(label.replace(" ", ""))
    return all(any(char == current for current in iterator) for char in abbreviation)


def _contains_label(query: str, label: str) -> bool:
    """Match a normalized category as complete words, never inside another word."""
    return bool(label and re.search(rf"(?:^| ){re.escape(label)}(?: |$)", query))


def find_named_product(products: list[dict], query_text: str) -> dict | None:
    """Find one unambiguous item explicitly named by the customer.

    Matching is derived from catalog names and model-like tokens, not from a
    hand-maintained product dictionary.
    """
    query = _normal(query_text)
    if not query:
        return None
    compact_query = query.replace(" ", "")
    scored: list[tuple[float, dict]] = []
    for product in products:
        name = _normal(str(product.get("name", "")))
        if not name:
            continue
        compact_name = name.replace(" ", "")
        if len(compact_name) >= 12 and compact_name in compact_query:
            return product

        name_tokens = set(name.split())
        query_tokens = set(query.split())
        overlap = name_tokens & query_tokens
        coverage = len(overlap) / max(1, len(name_tokens))
        identifiers = {
            token for token in name_tokens
            if len(token) >= 5 and any(char.isalpha() for char in token)
            and any(char.isdigit() for char in token)
        }
        identifier_hits = identifiers & query_tokens
        if identifier_hits or (len(overlap) >= 4 and coverage >= 0.72):
            scored.append((coverage + 2 * len(identifier_hits), product))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None
    if len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15:
        return scored[0][1]
    return None


async def resolve_category_candidates(query_text: str) -> tuple[str | None, list[str]]:
    """Resolve one real ES category or return close alternatives to clarify."""
    response = await elasticsearch.search({
        "size": 0,
        "aggs": {"categories": {"terms": {"field": "category_name.raw", "size": 1000}}},
    })
    query = _normal(query_text)
    categories = [bucket["key"] for bucket in response.get("aggregations", {}).get("categories", {}).get("buckets", [])]
    exact = [category for category in categories if _contains_label(query, _normal(category))]
    if exact:
        return max(exact, key=lambda item: len(_normal(item))), []

    compact_query = query.replace(" ", "")
    if 2 <= len(compact_query) <= 6:
        scored = sorted([
            (len(compact_query) / max(1, len(_normal(category).replace(" ", ""))), category)
            for category in categories if _is_subsequence(compact_query, _normal(category))
        ], reverse=True)
        if scored:
            if len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.12:
                return scored[0][1], []
            return None, [category for score, category in scored if score >= scored[0][0] - 0.12][:3]

    fuzzy = sorted([
        (SequenceMatcher(None, query, _normal(category)).ratio(), category)
        for category in categories if len(query) >= 4
        and SequenceMatcher(None, query, _normal(category)).ratio() >= 0.70
    ], reverse=True)
    if fuzzy:
        if len(fuzzy) == 1 or fuzzy[0][0] - fuzzy[1][0] >= 0.08:
            return fuzzy[0][1], []
        return None, [category for score, category in fuzzy if score >= fuzzy[0][0] - 0.08][:3]
    return None, []


async def resolve_category(query_text: str) -> str | None:
    """Discover a real category directly from Elasticsearch index values."""
    response = await elasticsearch.search({
        "size": 0,
        "aggs": {"categories": {"terms": {"field": "category_name.raw", "size": 1000}}},
    })
    query = _normal(query_text)
    categories = [bucket["key"] for bucket in response.get("aggregations", {}).get("categories", {}).get("buckets", [])]
    matches = [category for category in categories if _contains_label(query, _normal(category))]
    if matches:
        return max(matches, key=lambda item: len(_normal(item)))
    # Generic abbreviation support (TV, ML, MRCC ...).  It is only accepted
    # when it identifies one real catalog category unambiguously.
    compact_query = query.replace(" ", "")
    if 2 <= len(compact_query) <= 6:
        abbreviated = [
            (len(compact_query) / max(1, len(_normal(category).replace(" ", ""))), category)
            for category in categories if _is_subsequence(compact_query, _normal(category))
        ]
        abbreviated.sort(reverse=True)
        if abbreviated and (len(abbreviated) == 1 or abbreviated[0][0] - abbreviated[1][0] >= 0.12):
            return abbreviated[0][1]
    # Conservative typo recovery: require a close full-label match and an
    # unambiguous winner so generic/off-topic text is never routed as catalog.
    candidates = []
    for category in categories:
        label = _normal(category)
        score = SequenceMatcher(None, query, label).ratio()
        if len(query) >= 4 and score >= 0.84:
            candidates.append((score, category))
    candidates.sort(reverse=True)
    if len(candidates) == 1 or candidates and candidates[0][0] - candidates[1][0] >= 0.08:
        return candidates[0][1] if candidates else None
    return None


def _f(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _price(v: Any) -> float | None:
    value = _f(v)
    return value if value is not None and value > 0 else None


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
        "image_url": src.get("image_url") or None,
        "url": src.get("url") or None,
        "price_original": _price(src.get("original_price")),
        "price_sale": _price(src.get("sale_price")),
        "area_min_m2": area_min,
        "area_max_m2": area_max,
        "noise_db_min": _parse_noise_min(specs),
        "inverter": _parse_inverter(specs, name),
        "energy_stars": _parse_energy_stars(specs),
        "loai_may": _spec_find(specs, "loại máy"),
        "warranty_parts": _spec_find(specs, "bảo hành cục", "bảo hành linh kiện", "bảo hành sản phẩm")
        or src.get("warranty_policy"),
        "utilities": _spec_find(specs, "tiện ích"),
        "attributes": specs,
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


async def search_products(query: str, category: str | None = None, size: int = 10) -> list[dict]:
    """Tra sản phẩm theo tên/mã (dùng cho tool search_catalog khi khách nêu SP cụ thể).

    Khác get_products: full-text trên product_name/product_code (có fuzziness cho sai chính tả),
    tùy chọn giới hạn theo category. Trả về list dict đã normalize (rỗng nếu không khớp).
    """
    if not (query or "").strip():
        return []
    # cross_fields + operator AND: MỌI token (kể cả mã model) phải xuất hiện ở đâu đó ->
    # tên/mã lạ hoàn toàn sẽ trả 0 hit (điều kiện để rẽ sang nhánh làm giàu từ web),
    # trong khi mã đúng (dù brand nằm ở field brand, model ở product_name) vẫn khớp.
    must: list[dict] = [{
        "multi_match": {
            "query": query,
            "type": "cross_fields",
            "fields": ["product_name", "product_code", "brand"],
            "operator": "and",
        }
    }]
    if category:
        must.append({"term": {"category_name.raw": category}})
    body = {"size": size, "_source": _SOURCE, "query": {"bool": {"must": must}}}
    resp = await elasticsearch.search(body)
    hits = resp.get("hits", {}).get("hits", [])
    out = []
    for h in hits:
        src = h.get("_source", {})
        out.append(_normalize(src, src.get("category_name") or category or ""))
    return out
