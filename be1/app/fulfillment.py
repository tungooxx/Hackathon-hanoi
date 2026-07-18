"""Category-independent fulfilment capability.

Product-fit ontology never owns customer location.  A fulfilment provider
declares the context it needs and answers availability for any SKU/category.
Replace the prototype provider with a real store-stock adapter without
changing the chat graph or category profiles.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FulfillmentResult:
    available: bool
    message: str
    prototype: bool


@dataclass(frozen=True)
class RegionResolution:
    region: str | None
    candidates: list[str]


def _normal(value: str) -> str:
    return _normal_with_spaces(value).replace(" ", "")


def _normal_with_spaces(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _subsequence(short: str, long: str) -> bool:
    iterator = iter(long)
    return all(any(char == item for item in iterator) for char in short)


class FulfillmentProvider:
    capability = "inventory_by_region"

    def required_context(self, context: dict[str, str]) -> str | None:
        return None if context.get("region") else "region"

    def question(self, context_key: str) -> str:
        return "Anh/chị ở tỉnh/thành nào để em kiểm tra khả năng có hàng gần mình ạ?"

    async def check(self, sku: str, context: dict[str, str]) -> FulfillmentResult:
        raise NotImplementedError


class PrototypeFulfillmentProvider(FulfillmentProvider):
    """Demo adapter: every candidate is available in every supplied region."""

    def __init__(self) -> None:
        path = Path(__file__).resolve().parent.parent / "data" / "prototype_regions.json"
        self.regions: list[str] = json.loads(path.read_text(encoding="utf-8"))

    def resolve_region(self, text: str) -> RegionResolution:
        query = _normal(text)
        exact = [region for region in self.regions if _normal(region) == query]
        if exact:
            return RegionResolution(exact[0], [])
        if 2 <= len(query) <= 6:
            initial_matches = [
                region for region in self.regions
                if "".join(word[0] for word in re.findall(r"[A-Za-z]+", _normal_with_spaces(region))) == query
            ]
            if initial_matches:
                return RegionResolution(initial_matches[0], []) if len(initial_matches) == 1 \
                    else RegionResolution(None, initial_matches[:3])
            scored = sorted([
                (len(query) / len(_normal(region)), region)
                for region in self.regions if _subsequence(query, _normal(region))
            ], reverse=True)
            if scored:
                if len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.10:
                    return RegionResolution(scored[0][1], [])
                return RegionResolution(None, [region for score, region in scored if score >= scored[0][0] - 0.10][:3])
        return RegionResolution(None, [])

    async def check(self, sku: str, context: dict[str, str]) -> FulfillmentResult:
        region = context["region"]
        return FulfillmentResult(
            available=True,
            prototype=True,
            message=(f"Dạ có ạ. Trong prototype, mẫu anh/chị đang xem có hàng tại {region}. "
                     "Phần này đang dùng dữ liệu demo để minh hoạ kiểm tra theo khu vực ạ."),
        )


fulfillment_provider: FulfillmentProvider = PrototypeFulfillmentProvider()
