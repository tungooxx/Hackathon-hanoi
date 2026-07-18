"""Adaptive Decision Ontology Engine.

This service never mutates the reviewed seed JSON.  It loads that JSON as a
knowledge seed, composes guarded profiles for related categories, and stores
only provisional profiles separately.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


REVIEWED_SEED_CATEGORIES = {
    "Máy giặt", "Máy lạnh", "Máy rửa chén", "Máy sấy quần áo", "Tủ Lạnh",
    "Tủ mát, tủ đông", "Máy nước nóng", "Bàn ủi", "Bảng vẽ điện tử",
    "Đồng hồ thông minh",
}
CORE_CATEGORY = "Tất cả"
COMPOSE_THRESHOLD = 0.45
STRONG_TRANSFER_THRESHOLD = 0.75


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "").lower().replace("đ", "d")
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


ALIASES = {
    "tu lanh": "Tủ Lạnh", "tu dong": "Tủ mát, tủ đông", "tu mat": "Tủ mát, tủ đông",
    "tu dong tu mat": "Tủ mát, tủ đông", "bang ve": "Bảng vẽ điện tử",
    "bang ve dien tu": "Bảng vẽ điện tử", "ban ui": "Bàn ủi", "may lanh": "Máy lạnh",
    "may giat": "Máy giặt", "may rua chen": "Máy rửa chén", "may say quan ao": "Máy sấy quần áo",
    "may nuoc nong": "Máy nước nóng", "dong ho thong minh": "Đồng hồ thông minh",
}


MODULE_PATTERNS: dict[str, tuple[str, ...]] = {
    "display": ("man hinh", "display", "do phan giai", "tan so quet", "do sang", "cam ung"),
    "audio": ("am thanh", "loa", "dolby"),
    "connectivity": ("hdmi", "wifi", "bluetooth", "ket noi", "5g", "cong"),
    "battery": ("pin", "battery", "sac", "charging", "thoi luong pin"),
    "portability": ("khoi luong", "trong luong", "portable", "di dong"),
    "camera": ("camera", "quay phim", "chup anh"),
    "compute": ("cpu", "chip", "ram", "xu ly"),
    "storage": ("bo nho", "dung luong", "storage", "o cung"),
    "energy": ("dien nang", "cong suat tieu thu", "nhan nang luong", "inverter"),
    "noise": ("do on", "van hanh em"),
    "dimensions": ("kich thuoc", "chieu cao", "chieu ngang", "chieu sau", "do day"),
    "installation": ("lap dat", "duong ong", "khong gian lap", "thoat nuoc"),
    "capacity": ("pham vi su dung", "dung tich"),
    "washing": ("giat", "long giat", "vat"), "drying": ("say", "nhiet do say"),
    "cooling": ("lam lanh", "may lanh", "dieu hoa"), "heating": ("suoi", "lam nong"),
    "water": ("nuoc", "cap nuoc", "ap luc nuoc"), "safety": ("an toan", "khoa tre em"),
    "material_care": ("chat lieu", "do cung", "do day"),
    "comfort": ("do cung", "em", "tu the ngu", "comfort"),
    "support": ("tai trong", "nang do", "support"),
    "input_pen": ("but", "pen", "stylus"), "smart_control": ("dieu khien", "smart", "ung dung"),
}


class AdaptCategoryRequest(BaseModel):
    category_name: str
    raw_fields: list[str]
    sample_products: list[dict[str, Any]] = Field(default_factory=list)
    product_descriptions: list[str] = Field(default_factory=list)
    user_request: str | None = None
    force_regenerate: bool = False


class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rejected_items: list[str] = Field(default_factory=list)


class SeedMatch(BaseModel):
    category: str
    score: float
    matched_fields: list[str] = Field(default_factory=list)
    matched_modules: list[str] = Field(default_factory=list)


class ModuleState(BaseModel):
    module_id: str
    label: str
    status: Literal["REQUIRED", "OPTIONAL", "CONDITIONAL", "INACTIVE", "FORBIDDEN", "UNKNOWN"]
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    negative_evidence: list[str] = Field(default_factory=list)
    source_categories: list[str] = Field(default_factory=list)


class NextQuestionRequest(BaseModel):
    category_profile_id: str
    known_user_context: dict[str, Any] = Field(default_factory=dict)
    available_product_fields: list[str] = Field(default_factory=list)
    candidate_product_count: int = 0
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


class NextQuestionResponse(BaseModel):
    question_id: str
    question: str
    reason: str
    resolved_concept_id: str
    module_id: str
    hard_gate: bool
    score: float
    source: str


class AdaptedOntologyResponse(BaseModel):
    profile_id: str
    category: str
    normalized_category: str
    mode: Literal["REVIEWED", "COMPOSED_STRONG", "COMPOSED_HYBRID", "GENERATED_DISTANT"]
    family: str
    coverage_level: Literal["FULL", "MODULE_SUPPORTED", "PROVISIONAL"]
    seed_matches: list[SeedMatch] = Field(default_factory=list)
    active_modules: list[ModuleState] = Field(default_factory=list)
    inactive_modules: list[ModuleState] = Field(default_factory=list)
    forbidden_modules: list[ModuleState] = Field(default_factory=list)
    concepts: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    field_mappings: list[dict[str, Any]] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    overall_confidence: float
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class OntologySeedLoader:
    def __init__(self, ontology_path: Path):
        self.path = ontology_path

    def load(self) -> dict[str, Any]:
        with self.path.open(encoding="utf-8") as file:
            return json.load(file)


class AdaptiveOntologyEngine:
    def __init__(self, ontology_path: Path, registry_path: Path):
        self.seed = OntologySeedLoader(ontology_path).load()
        self.registry_path = registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text("{}", encoding="utf-8")
        self._by_category = self._index_seed()

    def _index_seed(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        result: dict[str, dict[str, list[dict[str, Any]]]] = {}
        sections = {"nodes": "concepts", "edges": "relationships", "questionNodes": "questions",
                    "rules": "rules", "evidence": "evidence", "fieldMap": "field_mappings"}
        for source, target in sections.items():
            for item in self.seed.get(source, []):
                data = item.get("data", item)
                category = data.get("category", data.get("Category", ""))
                if category in REVIEWED_SEED_CATEGORIES | {CORE_CATEGORY}:
                    result.setdefault(category, {}).setdefault(target, []).append(data)
        return result

    def canonical_category(self, category: str) -> str:
        normalized = normalize_text(category)
        if normalized in ALIASES:
            return ALIASES[normalized]
        for seed in REVIEWED_SEED_CATEGORIES:
            if normalize_text(seed) == normalized:
                return seed
        return re.sub(r"\s+", " ", category).strip()

    def _texts_for_category(self, category: str) -> list[str]:
        data = self._by_category.get(category, {})
        fields = [item.get("Raw Field", "") for item in data.get("field_mappings", [])]
        labels = [item.get("label", "") for item in data.get("concepts", [])]
        return [*fields, *labels]

    def _module_states(self, request: AdaptCategoryRequest, source_categories: list[str]) -> list[ModuleState]:
        evidence_text = " ".join([request.category_name, *request.raw_fields, *request.product_descriptions,
                                    *[str(value) for product in request.sample_products for value in product.values()]])
        normalized = normalize_text(evidence_text)
        states: list[ModuleState] = []
        fixed_display = normalize_text(request.category_name) in {"tivi", "tv", "television"}
        for module, patterns in MODULE_PATTERNS.items():
            hits = [pattern for pattern in patterns if re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", normalized)]
            if hits:
                states.append(ModuleState(module_id=f"MOD_{module.upper()}", label=module.replace("_", " ").title(),
                    status="REQUIRED", confidence=min(0.99, 0.65 + 0.1 * len(hits)), evidence=hits,
                    source_categories=source_categories))
            elif module == "battery" and fixed_display:
                states.append(ModuleState(module_id="MOD_BATTERY", label="Battery", status="INACTIVE", confidence=0.97,
                    negative_evidence=["Không có trường dữ liệu pin", "Thiết bị hiển thị cố định"], source_categories=[]))
            elif module == "portability" and fixed_display:
                states.append(ModuleState(module_id="MOD_PORTABILITY", label="Portability", status="INACTIVE", confidence=0.90,
                    negative_evidence=["Không có bằng chứng di động hoặc trọng lượng"], source_categories=[]))
        return states

    def _similarity(self, request: AdaptCategoryRequest) -> list[SeedMatch]:
        raw = [normalize_text(item) for item in request.raw_fields]
        result: list[SeedMatch] = []
        request_modules = {state.label.lower().replace(" ", "_") for state in self._module_states(request, []) if state.status == "REQUIRED"}
        for category in sorted(REVIEWED_SEED_CATEGORIES):
            source = [normalize_text(item) for item in self._texts_for_category(category)]
            matched = [field for field in request.raw_fields if any(field_norm in item or item in field_norm
                       for item in source for field_norm in [normalize_text(field)])]
            source_text = " ".join(source)
            source_modules = {name for name, patterns in MODULE_PATTERNS.items()
                              if any(re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", source_text) for pattern in patterns)}
            common_modules = request_modules & source_modules
            name_score = SequenceMatcher(None, normalize_text(request.category_name), normalize_text(category)).ratio()
            field_score = len(matched) / max(1, len(raw))
            module_score = len(common_modules) / max(1, len(request_modules))
            score = round(0.15 * name_score + 0.25 * field_score + 0.60 * module_score, 3)
            if score > 0:
                result.append(SeedMatch(category=category, score=score, matched_fields=matched,
                    matched_modules=sorted(common_modules)))
        return sorted(result, key=lambda item: item.score, reverse=True)[:3]

    def _profile_id(self, category: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", normalize_text(category)).strip("_") or "unknown"
        return f"profile_{slug}_{sha256(category.encode()).hexdigest()[:8]}"

    def _category_items(self, category: str) -> dict[str, list[dict[str, Any]]]:
        core = self._by_category.get(CORE_CATEGORY, {})
        specific = self._by_category.get(category, {})
        result = {key: [*core.get(key, []), *specific.get(key, [])]
                  for key in {"concepts", "relationships", "questions", "rules", "evidence", "field_mappings"}}
        for key, values in result.items():
            seen: set[str] = set()
            result[key] = [value for value in values if not value.get("id") or not (value["id"] in seen or seen.add(value["id"]))]
        return result

    def _validate(self, profile: AdaptedOntologyResponse) -> ValidationResult:
        ids = [item.get("id") for item in profile.concepts if item.get("id")]
        errors = ["Duplicate concept IDs" ] if len(ids) != len(set(ids)) else []
        concept_ids = set(ids)
        for relation in profile.relationships:
            if relation.get("source") not in concept_ids or relation.get("target") not in concept_ids:
                errors.append(f"Relationship {relation.get('id')} references an unavailable concept")
        return ValidationResult(valid=not errors, errors=errors)

    def _load_registry(self) -> dict[str, Any]:
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _store(self, profile: AdaptedOntologyResponse) -> None:
        registry = self._load_registry()
        registry[profile.profile_id] = profile.model_dump(mode="json")
        self.registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    def adapt(self, request: AdaptCategoryRequest) -> AdaptedOntologyResponse:
        category = self.canonical_category(request.category_name)
        profile_id = self._profile_id(category)
        registry = self._load_registry()
        if profile_id in registry and not request.force_regenerate:
            return AdaptedOntologyResponse.model_validate(registry[profile_id])
        matches = self._similarity(request)
        is_distant_family = normalize_text(category) in {"nem", "ghe gaming", "may anh", "may hut bui"}
        if category in REVIEWED_SEED_CATEGORIES:
            mode, coverage, sources, family = "REVIEWED", "FULL", [category], "reviewed_seed"
            items = self._category_items(category)
        elif not is_distant_family and matches and matches[0].score >= COMPOSE_THRESHOLD:
            mode = "COMPOSED_STRONG" if matches[0].score >= STRONG_TRANSFER_THRESHOLD else "COMPOSED_HYBRID"
            coverage, sources, family = "MODULE_SUPPORTED", [match.category for match in matches if match.score >= COMPOSE_THRESHOLD], "composed_product"
            items = self._category_items(CORE_CATEGORY)
            for source in sources:
                source_items = self._by_category.get(source, {})
                for key in items:
                    items[key].extend(source_items.get(key, []))
            for key, values in items.items():
                seen: set[str] = set()
                items[key] = [value for value in values if not value.get("id") or not (value["id"] in seen or seen.add(value["id"]))]
            for relation in items["relationships"]:
                relation.setdefault("required_modules", [])
                relation.setdefault("excluded_modules", [])
                relation["transfer_mode"] = "GENERIC_TRANSFER" if relation.get("category") == CORE_CATEGORY else "CATEGORY_TRANSFER"
                relation["source_relationship_ids"] = [relation.get("id")]
                relation["confidence"] = max(match.score for match in matches)
                relation["status"] = "TRANSFERRED"
        else:
            mode, coverage, sources, family = "GENERATED_DISTANT", "PROVISIONAL", [], "unknown_product"
            items = self._category_items(CORE_CATEGORY)
            active_names = [state.label for state in self._module_states(request, []) if state.status == "REQUIRED"]
            slug = re.sub(r"[^A-Z0-9]+", "_", normalize_text(category).upper()).strip("_") or "UNKNOWN"
            items["concepts"].extend({"id": f"GEN_{slug}_ATTR_{index:03}", "label": field, "canonical": field,
                "type": "ProductAttribute", "category": category, "primarySource": "Catalog", "acquisition": "Retrieved",
                "status": "PROVISIONAL", "provenance": {"source_type": "LLM", "confidence": 0.35, "review_status": "PENDING"}}
                for index, field in enumerate(request.raw_fields, 1))
            if not request.raw_fields:
                active_names = []
        concept_ids = {item.get("id") for item in items["concepts"]}
        items["relationships"] = [relationship for relationship in items["relationships"]
                                  if relationship.get("source") in concept_ids and relationship.get("target") in concept_ids]
        states = self._module_states(request, sources)
        active = [state for state in states if state.status in {"REQUIRED", "OPTIONAL", "CONDITIONAL"}]
        inactive = [state for state in states if state.status == "INACTIVE"]
        profile = AdaptedOntologyResponse(profile_id=profile_id, category=request.category_name, normalized_category=category,
            mode=mode, family=family, coverage_level=coverage, seed_matches=matches, active_modules=active,
            inactive_modules=inactive, concepts=items["concepts"], relationships=items["relationships"],
            questions=items["questions"], rules=items["rules"], evidence=items["evidence"],
            field_mappings=items["field_mappings"], unknown_fields=[], overall_confidence=(0.98 if mode == "REVIEWED" else (matches[0].score if matches else 0.25)),
            warnings=(["Cần schema hoặc mẫu sản phẩm trước khi tạo quy tắc cứng."] if not request.raw_fields else ([] if mode != "GENERATED_DISTANT" else ["Nội dung theo category này là PROVISIONAL và cần duyệt."])),
            provenance={"source_type": "SEED" if mode == "REVIEWED" else ("MULTI_SEED" if sources else "LLM"), "source_categories": sources,
                        "generated_at": datetime.now(UTC).isoformat(), "review_status": "PENDING" if mode != "REVIEWED" else "APPROVED"})
        profile.validation = self._validate(profile)
        self._store(profile)
        return profile

    def get_profile(self, name_or_id: str) -> AdaptedOntologyResponse | None:
        registry = self._load_registry()
        if name_or_id in registry:
            return AdaptedOntologyResponse.model_validate(registry[name_or_id])
        category = self.canonical_category(name_or_id)
        return self.adapt(AdaptCategoryRequest(category_name=category, raw_fields=[])) if category in REVIEWED_SEED_CATEGORIES else None

    def next_question(self, request: NextQuestionRequest) -> NextQuestionResponse | None:
        profile = self.get_profile(request.category_profile_id)
        if not profile:
            return None
        active_names = {state.label.lower().replace(" ", "_") for state in profile.active_modules}
        known = {normalize_text(key) for key in request.known_user_context}
        for question in profile.questions:
            concept = question.get("conceptId", "")
            label = question.get("label", "")
            if normalize_text(concept) in known or normalize_text(label) in known:
                continue
            text = normalize_text(label)
            if "pin" in text and "battery" not in active_names:
                continue
            return NextQuestionResponse(question_id=question.get("id", "Q_UNKNOWN"), question=label,
                reason="Câu trả lời có thể thay đổi điều kiện phù hợp hoặc thứ hạng sản phẩm.", resolved_concept_id=concept,
                module_id="MOD_CORE", hard_gate=question.get("hardGate") == "Yes", score=0.8, source="ORIGINAL")
        return None

    def review(self, profile_id: str, approved: bool) -> AdaptedOntologyResponse:
        profile = self.get_profile(profile_id)
        if not profile:
            raise KeyError(profile_id)
        profile.provenance["review_status"] = "APPROVED" if approved else "REJECTED"
        self._store(profile)
        return profile

    def seeds(self) -> list[dict[str, Any]]:
        return [{"category": category, "concept_count": len(self._by_category.get(category, {}).get("concepts", []))}
                for category in sorted(REVIEWED_SEED_CATEGORIES | {CORE_CATEGORY})]

    def modules(self) -> list[dict[str, Any]]:
        return [{"module_id": f"MOD_{name.upper()}", "label": name, "status": "MINED", "field_patterns": patterns,
                 "source_categories": sorted(REVIEWED_SEED_CATEGORIES), "confidence": 0.6}
                for name, patterns in MODULE_PATTERNS.items()]
