"""LLM-compiled, cached runtime decision profiles.

This is the replacement boundary for hand-maintained concept-to-field rules:
the compiler receives ontology questions and real Elasticsearch evidence, then
returns only mappings the current catalog can support.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_SMALL


class RuntimeQuestion(BaseModel):
    slot: str = Field(description="Stable snake_case identifier derived from the ontology concept")
    question: str
    question_type: Literal["boolean", "choice", "numeric"]
    possible_answers: list[str] = Field(default_factory=list)
    field: str = Field(description="Exact field key from catalog attributes or a top-level catalog field")
    operation: Literal["equals", "contains", "max", "min", "range"]
    hard_gate: bool = False


class RuntimeProfile(BaseModel):
    category: str = ""
    catalog_fingerprint: str = ""
    questions: list[RuntimeQuestion] = Field(default_factory=list)
    provisional: bool


_ROOT = Path(__file__).resolve().parent.parent
_CACHE = _ROOT / "data" / "runtime_profiles.json"


def _fingerprint(category: str, products: list[dict]) -> str:
    fields = sorted({key for product in products for key in product.get("attributes", {})})
    sample = [{key: value for key, value in product.get("attributes", {}).items()} for product in products[:3]]
    return sha256(json.dumps([category, fields, sample], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _load_cache() -> dict[str, Any]:
    return json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}


def _save_cache(cache: dict[str, Any]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


async def compile_profile(category: str, ontology_questions: list[dict], products: list[dict]) -> RuntimeProfile:
    """Create or reuse a profile from ontology questions and actual catalog evidence."""
    fingerprint = _fingerprint(category, products)
    cache = _load_cache()
    cached = cache.get(category)
    if cached and cached.get("catalog_fingerprint") == fingerprint:
        return RuntimeProfile.model_validate(cached)

    from langchain_openai import ChatOpenAI

    fields = sorted({key for product in products for key in product.get("attributes", {})})
    samples = [product.get("attributes", {}) for product in products[:3]]
    prompt = {
        "category": category,
        "ontology_questions": ontology_questions,
        "catalog_attribute_keys": fields,
        "catalog_samples": samples,
        "instructions": (
            "Map only questions that can be evaluated from an exact catalog field. "
            "Do not invent fields, values, weights, or questions. Omit questions with no measurable catalog effect. "
            "Use hard_gate only when an answer determines eligibility."
        ),
    }
    model = ChatOpenAI(model=LLM_MODEL_SMALL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY, temperature=0)
    result = await model.with_structured_output(RuntimeProfile).ainvoke([
        ("system", "You compile safe product-decision mappings from ontology to catalog evidence."),
        ("user", json.dumps(prompt, ensure_ascii=False)),
    ])
    profile = result.model_copy(update={"category": category, "catalog_fingerprint": fingerprint, "provisional": True})
    cache[category] = profile.model_dump(mode="json")
    _save_cache(cache)
    return profile
