"""Client gọi BE2 của Kiên. BE2_BASE_URL rỗng -> đọc fixture local.

Contract với Kiên: GET {BE2_BASE_URL}/products?category=may_lanh
trả về list JSON các product đã normalize (xem fixtures/may_lanh.json làm mẫu shape).
"""
import json
from functools import lru_cache

import httpx

from .config import BE2_BASE_URL, ROOT


@lru_cache(maxsize=None)
def _fixture(category: str) -> list[dict]:
    path = ROOT / "fixtures" / f"{category}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


async def get_products(category: str) -> list[dict]:
    if not BE2_BASE_URL:
        return _fixture(category)
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{BE2_BASE_URL}/products", params={"category": category})
        resp.raise_for_status()
        return resp.json()
