"""LLM-compiled, cached runtime decision profiles.

This is the replacement boundary for hand-maintained concept-to-field rules:
the compiler receives ontology questions and real Elasticsearch evidence, then
returns only mappings the current catalog can support.
"""
from __future__ import annotations

import json
import logging
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from filelock import FileLock

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_SMALL

logger = logging.getLogger(__name__)


class RuntimeQuestion(BaseModel):
    slot: str = Field(description="Stable snake_case identifier derived from the ontology concept")
    question: str
    question_type: Literal["boolean", "choice", "numeric"]
    possible_answers: list[str] = Field(default_factory=list)
    answer_values: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Customer answer to exact raw catalog values for the selected field",
    )
    field: str = Field(description="Exact field key from catalog attributes or a top-level catalog field")
    operation: Literal["equals", "contains", "max", "min", "range"]
    ordered_values: list[str] = Field(
        default_factory=list,
        description="Exact catalog values ordered from lower/less capable to higher/more capable; only for ordinal fields",
    )
    unit: str = Field(
        default="",
        description="Customer-facing unit for numeric field, copied from catalog evidence when applicable",
    )
    hard_gate: bool = False
    source: Literal["ontology", "generated"] = "ontology"
    customer_effort: float = Field(ge=0.0, le=1.0, description="Expected effort for an ordinary shopper")
    requires_technical_knowledge: bool = Field(
        description="True when answering requires knowing a technical specification rather than a normal shopping need"
    )
    boolean_true_values: list[str] = Field(
        default_factory=list, description="Exact raw catalog values eligible when the customer means true"
    )
    boolean_false_values: list[str] = Field(
        default_factory=list, description="Exact raw catalog values eligible when false; empty means no filtering"
    )


class RuntimeProfile(BaseModel):
    category: str = ""
    catalog_fingerprint: str = ""
    questions: list[RuntimeQuestion] = Field(default_factory=list)
    provisional: bool


_ROOT = Path(__file__).resolve().parent.parent
_CACHE = _ROOT / "data" / "runtime_profiles.json"
_CACHE_LOCK = FileLock(f"{_CACHE}.lock")
_PROFILE_SCHEMA_VERSION = 10


def _fingerprint(category: str, products: list[dict]) -> str:
    fields = sorted({key for product in products for key in product.get("attributes", {})})
    catalog_values = sorted(
        json.dumps(product.get("attributes", {}), ensure_ascii=False, sort_keys=True, default=str)
        for product in products
    )
    return sha256(json.dumps(
        [_PROFILE_SCHEMA_VERSION, category, fields, catalog_values], ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()


def _load_cache() -> dict[str, Any]:
    return json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}


def _save_cache(category: str, profile: dict[str, Any]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[category] = profile
        temporary = _CACHE.with_suffix(f"{_CACHE.suffix}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, _CACHE)


def _validate_questions(
    questions: list[RuntimeQuestion],
    available_fields: set[str],
    catalog_values: dict[str, list[str]],
) -> tuple[list[RuntimeQuestion], list[str]]:
    """Keep only executable mappings grounded in this exact catalog."""
    valid: list[RuntimeQuestion] = []
    errors: list[str] = []
    seen_slots: set[str] = set()
    for index, question in enumerate(questions):
        prefix = f"questions[{index}]"
        if question.field not in available_fields:
            errors.append(f"{prefix}.field is not one exact catalog_attribute_key: {question.field!r}")
            continue
        if question.slot in seen_slots:
            errors.append(f"{prefix}.slot must be unique: {question.slot!r}")
            continue
        if question.question_type == "numeric" and question.operation not in {"min", "max", "range"}:
            errors.append(f"{prefix}.operation is unsupported for numeric questions: {question.operation!r}")
            continue
        if not question.question.strip() or re.fullmatch(r"[A-Z][A-Z0-9_]+", question.question.strip()):
            errors.append(f"{prefix}.question must be a complete customer-facing Vietnamese sentence, not an ID")
            continue
        observed = set(catalog_values.get(question.field, []))
        mapped_values = [raw for items in question.answer_values.values() for raw in items]
        if question.question_type == "boolean":
            if (not question.boolean_true_values
                    or any(not raw or raw not in observed for raw in question.boolean_true_values)
                    or any(not raw or raw not in observed for raw in question.boolean_false_values)):
                errors.append(f"{prefix} boolean true/false values are not grounded in {question.field!r}")
                continue
        elif question.question_type == "choice":
            if not mapped_values or any(not raw or raw not in observed for raw in mapped_values):
                errors.append(f"{prefix}.answer_values must contain only non-empty exact raw values for {question.field!r}")
                continue
        if question.ordered_values and any(
            raw not in observed and raw not in question.answer_values
            for raw in question.ordered_values
        ):
            errors.append(
                f"{prefix}.ordered_values must contain catalog values or executable answer keys "
                f"for {question.field!r}"
            )
            continue
        if question.requires_technical_knowledge or question.customer_effort > 0.7:
            errors.append(f"{prefix} is unsuitable for an ordinary shopper; omit it or ask a lower-effort need")
            continue
        seen_slots.add(question.slot)
        valid.append(question)
    return valid, errors


def _cached_profile(category: str, products: list[dict], *, require_fingerprint: bool) -> RuntimeProfile | None:
    """Load a cache entry only when it remains executable for this catalog."""
    fingerprint = _fingerprint(category, products)
    fields = sorted({key for product in products for key in product.get("attributes", {})})
    standard_fields = ["price_sale", "price_original"]
    values = {
        field: sorted({str(product.get("attributes", {}).get(field)) for product in products
                       if product.get("attributes", {}).get(field) not in (None, "")})[:20]
        for field in fields
    }
    values.update({
        field: sorted({str(product.get(field)) for product in products if product.get(field) is not None})[:20]
        for field in standard_fields
    })
    cached = _load_cache().get(category)
    if not cached or (require_fingerprint and cached.get("catalog_fingerprint") != fingerprint):
        return None
    try:
        cached_profile = RuntimeProfile.model_validate(cached)
        cached_valid, cached_errors = _validate_questions(
            cached_profile.questions, set([*fields, *standard_fields]), values
        )
    except (ValidationError, TypeError, ValueError) as error:
        logger.warning("Rejected runtime profile cache for %r: %s", category, error)
        return None
    if cached_errors or len(cached_valid) != len(cached_profile.questions):
        if require_fingerprint or not cached_valid:
            logger.warning("Rejected runtime profile cache for %r: %s", category, cached_errors)
            return None
        # A stale snapshot may contain one mapping whose raw values vanished
        # after a catalog update.  Keep the independently validated questions
        # instead of demoting the entire category to budget-only fallback.
        logger.info("Reused %d compatible runtime questions for %r; dropped: %s",
                    len(cached_valid), category, cached_errors)
    return cached_profile.model_copy(update={"questions": cached_valid})


def get_cached_profile(category: str, products: list[dict]) -> RuntimeProfile | None:
    """Return an exact catalog-fingerprint cache hit without compiling."""
    return _cached_profile(category, products, require_fingerprint=True)


def get_compatible_cached_profile(category: str, products: list[dict]) -> RuntimeProfile | None:
    """Reuse a stale snapshot only when every retained mapping still validates.

    ES data can change order or receive harmless catalog updates between a
    prewarm and a chat turn.  The profile's executable field/value validation
    is stricter than a fingerprint alone, so it is safe to retain the valid
    subset rather than degrading the whole category to budget-only fallback.
    """
    return _cached_profile(category, products, require_fingerprint=False)


async def compile_profile(category: str, ontology_questions: list[dict], products: list[dict]) -> RuntimeProfile:
    """Create or reuse a profile from ontology questions and actual catalog evidence."""
    fingerprint = _fingerprint(category, products)
    fields = sorted({key for product in products for key in product.get("attributes", {})})
    standard_fields = ["price_sale", "price_original"]
    samples = [product.get("attributes", {}) for product in products[:3]]
    values = {
        field: sorted({str(product.get("attributes", {}).get(field)) for product in products
                       if product.get("attributes", {}).get(field) not in (None, "")})[:20]
        for field in fields
    }
    values.update({
        field: sorted({str(product.get(field)) for product in products if product.get(field) is not None})[:20]
        for field in standard_fields
    })

    if cached_profile := get_cached_profile(category, products):
        return cached_profile

    from langchain_openai import ChatOpenAI
    # The adaptive ontology determines which broad decision modules have
    # evidence in this category; the LLM still has to bind any question to an
    # exact catalog field/value before it reaches the chat runtime.
    try:
        from .adaptive_ontology import (
            ALIASES,
            REVIEWED_SEED_CATEGORIES,
            AdaptCategoryRequest,
            AdaptiveOntologyEngine,
            normalize_text,
        )
        canonical = ALIASES.get(normalize_text(category), category)
        if canonical in REVIEWED_SEED_CATEGORIES:
            # Reviewed categories already have an approved ontology seed.
            # They must never be materialized into adaptive_profiles.json.
            active_modules = []
        else:
            engine = AdaptiveOntologyEngine(
                _ROOT.parent / "data" / "ontology_data.json",
                _ROOT / "data" / "adaptive_profiles.json",
            )
            adapted = engine.adapt(AdaptCategoryRequest(
                category_name=category, raw_fields=fields, sample_products=samples,
            ))
            active_modules = [module.label for module in adapted.active_modules]
    except Exception:
        active_modules = []
    prompt = {
        "category": category,
        "ontology_questions": [{
            "concept_id": question.get("conceptId"),
            "question": question.get("label"),
            "question_type": question.get("questionType"),
            "possible_answers": question.get("possibleAnswers"),
            "hard_gate": question.get("hardGate"),
        } for question in ontology_questions],
        "catalog_attribute_keys": [*fields, *standard_fields],
        "catalog_samples": samples,
        "catalog_attribute_values": values,
        "adaptive_modules_with_catalog_evidence": active_modules,
        "instructions": (
            "First map approved ontology_questions that can be evaluated from an exact catalog field. "
            "If those leave meaningful catalog variation uncovered, you may add at most four "
            "source='generated' provisional questions. Each generated question must be a simple, "
            "complete human-facing Vietnamese sentence derived from exactly one catalog field and its "
            "raw values; never invent a product fact, threshold, feature, or answer. "
            "Prefer fields belonging to adaptive_modules_with_catalog_evidence. "
            "For every boolean or choice question, answer_values must map every customer answer "
            "to exact strings from catalog_attribute_values; omit the question if that is impossible. "
            "For boolean questions also populate boolean_true_values and boolean_false_values using only exact raw "
            "catalog strings. true values must be non-empty. false values may be empty when false means the feature "
            "is not required and should not filter products. "
            "For a numeric field, set its catalog unit and use min/max/range according to its meaning. "
            "If that unit is a technical metric an ordinary shopper may not know, ask a qualitative, outcome-based "
            "preference that can be interpreted as higher/lower ranking; do not ask them to choose a numeric threshold. "
            "Never invent an unrelated proxy. For an ordinal field such as resolution, provide ordered_values using "
            "only exact catalog strings, in low-to-high order, and use min when wording supports "
            "'or higher'. Do not make ordinal or numeric questions unless the catalog evidence supports it. "
            "Questions must be comfortable for a regular shopper. If an exact raw technical value cannot "
            "be asked in plain Vietnamese without making the shopper choose an unfamiliar specification, "
            "omit that field rather than asking it. Every question must make 'không rõ/không ưu tiên' an "
            "acceptable answer; that means the criterion is skipped, not filtered. "
            "For every question, estimate customer_effort from 0 to 1 and set requires_technical_knowledge. "
            "Omit questions requiring technical knowledge or high effort even if they could change ranking. "
            "Do not invent fields, values, weights, or questions beyond those catalog-grounded provisional questions. "
            "Omit questions with no measurable catalog effect. "
            "Use hard_gate only when an answer determines eligibility."
        ),
    }
    model = ChatOpenAI(model=LLM_MODEL_SMALL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY, temperature=0)
    structured_model = model.with_structured_output(RuntimeProfile)
    errors: list[str] = []
    result: RuntimeProfile | None = None
    valid_questions: list[RuntimeQuestion] = []
    for _attempt in range(2):
        request = dict(prompt)
        if errors:
            request["previous_output_validation_errors"] = errors
            request["retry_instruction"] = "Correct every validation error. Do not repeat invalid questions."
        result = await structured_model.ainvoke([
            ("system", "You compile safe product-decision mappings from ontology to catalog evidence."),
            ("user", json.dumps(request, ensure_ascii=False)),
        ])
        valid_questions, errors = _validate_questions(
            result.questions, set([*fields, *standard_fields]), values
        )
        if valid_questions:
            break
    assert result is not None
    result = result.model_copy(update={"questions": valid_questions})
    profile = result.model_copy(update={"category": category, "catalog_fingerprint": fingerprint, "provisional": True})
    _save_cache(category, profile.model_dump(mode="json"))
    return profile
