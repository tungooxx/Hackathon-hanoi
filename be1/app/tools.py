"""Tool layer cho nhánh "sản phẩm lạ" — các hàm agent gọi được qua LLM bind_tools.

Gồm: web_search (Tavily qua httpx), fetch_product_specs (web + trích thông số),
search_catalog / filter_catalog (bọc quanh Elasticsearch + filtering/scoring).

MOCK_LLM=1 hoặc thiếu TAVILY_API_KEY -> web_search trả fixture offline, luồng chạy
không cần internet. Mọi tool là async, trả JSON-serializable để nạp lại vào hội thoại
tool-calling.
"""
import json
import re

import httpx

from . import product_repo
from .config import (
    MOCK_LLM,
    TAVILY_API_KEY,
    TAVILY_BASE_URL,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TIMEOUT_SECONDS,
)
from .filtering import apply_hard_filters
from .scoring import rank_top3


# ---------------- web_search ----------------

def _mock_web_results(query: str) -> list[dict]:
    """Fixture offline: trả vài kết quả 'giống web' để demo/test không cần internet."""
    low = query.lower()
    hp = None
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*hp", low):
        hp = m.group(1)
    title = f"Thông số {query.strip()[:60]}"
    content = (
        f"{query.strip()} là máy lạnh inverter"
        + (f" công suất {hp}HP" if hp else "")
        + ". Công suất phù hợp phòng khoảng "
        + (f"{int(float(hp) * 12) if hp else 15}m². " if hp else "15m². ")
        + "Giá tham khảo khoảng 9.000.000đ - 12.000.000đ. Tiết kiệm điện, độ ồn ~24dB, "
        "hiệu suất năng lượng 5 sao."
    )
    return [
        {"title": title, "url": "https://example.com/mock-1", "content": content},
        {"title": f"Đánh giá {query.strip()[:40]}", "url": "https://example.com/mock-2",
         "content": "Model được đánh giá tốt về độ bền và tiết kiệm điện trong tầm giá."},
    ]


async def web_search(query: str, max_results: int | None = None) -> list[dict]:
    """Tìm trên internet, trả list {title, url, content}. Fixture khi offline/thiếu key."""
    max_results = max_results or WEB_SEARCH_MAX_RESULTS
    if MOCK_LLM or not TAVILY_API_KEY:
        return _mock_web_results(query)[:max_results]
    url = TAVILY_BASE_URL.rstrip("/") + "/search"
    body = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    async with httpx.AsyncClient(timeout=WEB_SEARCH_TIMEOUT_SECONDS) as client:
        for attempt in range(3):  # kết nối lạnh -> retry
            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 2:
                    return []
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in data.get("results", [])
    ]


# ---------------- fetch_product_specs (web + trích thông số) ----------------

def _mock_extract_specs(name: str, results: list[dict]) -> dict:
    """Trích thông số dạng heuristic từ nội dung web (dùng khi MOCK_LLM)."""
    blob = " ".join(r.get("content", "") for r in results)
    low = blob.lower()
    slots: dict = {}
    prices = [float(x.replace(".", "").replace(",", "")) for x in re.findall(r"\d[\d.]{6,}", blob)]
    if prices:
        slots["budget_max"] = max(prices)
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*m", low):
        slots["area_m2"] = float(m.group(1).replace(",", "."))
    category = "may_lanh" if any(k in low for k in ("máy lạnh", "may lanh", "điều hòa", "inverter")) else None
    return {
        "product_name": name,
        "found": bool(results),
        "category": category,
        "brand": None,
        "catalog_slots": slots,
        "key_specs": {"raw": blob[:400]},
        "summary": (blob[:280] + "…") if blob else "Không tìm thấy thông tin trên web.",
    }


async def fetch_product_specs(product_name: str) -> dict:
    """Tra web thông số 1 sản phẩm -> dict {product_name, category, catalog_slots, key_specs, summary}.

    catalog_slots là các slot đã suy ra để tra/lọc trong catalog (budget_max, area_m2, brand...).
    """
    results = await web_search(product_name, max_results=WEB_SEARCH_MAX_RESULTS)
    if MOCK_LLM:
        return _mock_extract_specs(product_name, results)
    # LLM thật: trích structured (lazy import tránh vòng import với llm.py)
    from . import llm

    return await llm.extract_web_specs(product_name, results)


# ---------------- catalog tools ----------------

async def search_catalog(query: str, category: str | None = None) -> list[dict]:
    """Tra sản phẩm cụ thể trong Elasticsearch theo tên/mã. Trả list SP đã normalize."""
    return await product_repo.search_products(query, category=category)


async def filter_catalog(category: str, slots: dict, priorities: list[str] | None = None) -> list[dict]:
    """Lọc + xếp hạng top 3 SP trong 1 category theo slot cứng + ưu tiên (bọc filtering/scoring)."""
    products = await product_repo.get_products(category)
    candidates = apply_hard_filters(products, slots or {})
    if not candidates:
        return []
    return rank_top3(candidates, priorities or [])


# ---------------- schemas cho LLM bind_tools ----------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Tìm thông tin trên internet khi catalog nội bộ không có. Trả các đoạn nội dung liên quan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Câu truy vấn tìm kiếm"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_product_specs",
            "description": "Tra thông số kỹ thuật của MỘT sản phẩm cụ thể trên web (giá, công suất, diện tích phù hợp, độ ồn...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Tên/mã sản phẩm nguyên văn khách nêu"},
                },
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Tra sản phẩm cụ thể trong kho nội bộ (Elasticsearch) theo tên/mã.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string", "description": "Loại SP (may_lanh, tu_lanh...) nếu biết"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_catalog",
            "description": "Lọc & xếp hạng top sản phẩm trong kho theo category + tiêu chí (budget_max, area_m2, brand) và ưu tiên.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "slots": {"type": "object", "description": "budget_max, area_m2, brand, needs_heating..."},
                    "priorities": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category"],
            },
        },
    },
]

# tên tool -> hàm async thực thi (dùng trong vòng lặp bind_tools)
TOOL_FUNCS = {
    "web_search": lambda a: web_search(a["query"], a.get("max_results")),
    "fetch_product_specs": lambda a: fetch_product_specs(a["product_name"]),
    "search_catalog": lambda a: search_catalog(a["query"], a.get("category")),
    "filter_catalog": lambda a: filter_catalog(a["category"], a.get("slots", {}), a.get("priorities")),
}


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
