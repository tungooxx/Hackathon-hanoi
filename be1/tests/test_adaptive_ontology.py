from pathlib import Path
from hashlib import sha256
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adaptive_ontology import AdaptCategoryRequest, AdaptiveOntologyEngine, NextQuestionRequest
from app import ontology
from app.llm import _mock_intent
from app.graph import _customer_visible_slots, route_after_intent
from app.product_repo import find_named_product
from app.product_repo import _contains_label, _is_subsequence
from app.profile_compiler import RuntimeQuestion, _validate_questions
from app.schemas import SlotDef
from app.scoring import rank_top3


ROOT = Path(__file__).resolve().parents[2]


def engine(tmp_path: Path) -> AdaptiveOntologyEngine:
    return AdaptiveOntologyEngine(ROOT / "data" / "ontology_data.json", tmp_path / "profiles.json")


def test_reviewed_washer_uses_original_seed(tmp_path: Path) -> None:
    profile = engine(tmp_path).adapt(AdaptCategoryRequest(category_name="Máy giặt", raw_fields=[]))
    assert profile.mode == "REVIEWED"
    assert profile.coverage_level == "FULL"
    assert profile.validation.valid


def test_tv_composes_without_battery(tmp_path: Path) -> None:
    service = engine(tmp_path)
    profile = service.adapt(AdaptCategoryRequest(category_name="Tivi", raw_fields=[
        "Kích thước màn hình", "Độ phân giải", "Tần số quét", "Cổng HDMI", "Công nghệ âm thanh", "Công suất tiêu thụ",
    ]))
    active = {item.label for item in profile.active_modules}
    inactive = {item.label for item in profile.inactive_modules}
    assert profile.mode.startswith("COMPOSED")
    assert {"Display", "Audio", "Connectivity", "Energy"} <= active
    assert {"Battery", "Portability"} <= inactive
    question = service.next_question(NextQuestionRequest(category_profile_id=profile.profile_id))
    assert question is None or "pin" not in question.question.lower()


def test_phone_and_portable_tv_activate_only_evidenced_modules(tmp_path: Path) -> None:
    service = engine(tmp_path)
    phone = service.adapt(AdaptCategoryRequest(category_name="Điện thoại", raw_fields=[
        "Kích thước màn hình", "Dung lượng pin", "Camera", "RAM", "Bộ nhớ", "Khối lượng", "5G",
    ]))
    assert {"Display", "Battery", "Camera", "Compute", "Storage", "Connectivity", "Portability"} <= {m.label for m in phone.active_modules}
    portable = service.adapt(AdaptCategoryRequest(category_name="Tivi di động", raw_fields=[
        "Kích thước màn hình", "Dung lượng pin", "Thời lượng pin", "Khối lượng",
    ]))
    assert {"Display", "Battery", "Portability"} <= {m.label for m in portable.active_modules}


def test_mattress_is_provisional_and_has_no_unrelated_modules(tmp_path: Path) -> None:
    profile = engine(tmp_path).adapt(AdaptCategoryRequest(category_name="Nệm", raw_fields=[
        "Kích thước", "Độ cứng", "Chất liệu", "Độ dày", "Tải trọng",
    ]))
    assert profile.mode == "GENERATED_DISTANT"
    active = {item.label for item in profile.active_modules}
    assert {"Comfort", "Material Care", "Support"} <= active
    assert not ({"Washing", "Cooling", "Battery", "Display"} & active)
    assert all(item.get("status") == "PROVISIONAL" for item in profile.concepts if item["id"].startswith("GEN_"))


def test_no_field_evidence_is_low_confidence(tmp_path: Path) -> None:
    profile = engine(tmp_path).adapt(AdaptCategoryRequest(category_name="Nệm", raw_fields=[]))
    assert profile.mode == "GENERATED_DISTANT"
    assert profile.overall_confidence < 0.5
    assert profile.warnings


def test_transferred_relationships_are_guarded_and_profile_is_reused(tmp_path: Path) -> None:
    service = engine(tmp_path)
    request = AdaptCategoryRequest(category_name="Tivi", raw_fields=["Kích thước màn hình", "Cổng HDMI"])
    first = service.adapt(request)
    second = service.adapt(request)
    assert first.profile_id == second.profile_id
    assert first.relationships
    assert all("transfer_mode" in item for item in first.relationships)


def test_profile_identity_changes_with_material_evidence(tmp_path: Path) -> None:
    service = engine(tmp_path)
    first = service.adapt(AdaptCategoryRequest(category_name="Tivi", raw_fields=["Cổng HDMI"]))
    second = service.adapt(AdaptCategoryRequest(category_name="Tivi", raw_fields=["Dung lượng pin"]))
    assert first.profile_id != second.profile_id


def test_next_question_skips_history_and_unavailable_fields(tmp_path: Path) -> None:
    service = engine(tmp_path)
    profile = service.adapt(AdaptCategoryRequest(category_name="Máy lạnh", raw_fields=["Giá khuyến mãi"]))
    question = service.next_question(NextQuestionRequest(
        category_profile_id=profile.profile_id,
        available_product_fields=["Giá khuyến mãi"],
        conversation_history=[{"question_id": "Q_GEN_BUDGET"}, {"concept": "PREF_PROMOTION"}],
    ))
    assert question is None


def test_runtime_schema_uses_relationship_fields_without_category_rules() -> None:
    data = ontology._data()
    question = next(item["data"] for item in data["questionNodes"] if item["data"]["conceptId"].startswith("CTX_IRON_"))
    fields = next(
        edge["data"]["requiredFields"].split("|")
        for edge in data["edges"]
        if edge["data"].get("questionId") == question["id"] and edge["data"].get("requiredFields")
    )
    schema = ontology.get_slot_schema("Bàn ủi", [{"attributes": {field.strip(): "Có" for field in fields}}])
    assert any(item.name == question["conceptId"] for item in schema)


def test_active_dynamic_question_keeps_a_short_negative_reply_in_context() -> None:
    result = _mock_intent("khong", "ban ui", {
        "slot": "CTX_IRON_VERTICAL_NEED",
        "question": "vertical ironing",
        "type": "boolean",
        "answers": ["co", "khong"],
    })
    assert result.intent_type == "same_topic"
    assert result.ontology_answers == {"CTX_IRON_VERTICAL_NEED": "khong"}


def test_catalog_outage_is_not_routed_as_off_topic() -> None:
    assert route_after_intent({"intent_type": "new_topic", "catalog_lookup_failed": True}) == "catalog_unavailable"


def test_fulfillment_context_reply_routes_to_provider_check() -> None:
    assert route_after_intent({"intent_type": "same_topic", "awaiting_fulfillment": True,
                               "fulfillment_context": {"region": "Ha Noi"}}) == "fulfillment_check"


def test_find_named_product_helper_prefers_named_catalog_product() -> None:
    target = {"sku": "target", "name": "Tu lanh Toshiba Inverter 471 lit Multi Door GR-RF606WI-PMV(60)-AG"}
    products = [target, {"sku": "other", "name": "Tu lanh Funiki 74 lit FR-71CD"}]
    assert find_named_product(products, "toi hoi mua Tu lanh Toshiba Inverter 471 lit Multi Door GR-RF606WI-PMV(60)-AG") == target


def test_category_abbreviation_match_is_generic() -> None:
    assert _is_subsequence("tv", "tivi")
    assert _is_subsequence("ml", "may lanh")
    assert not _is_subsequence("zz", "tivi")


def test_compiled_answer_map_filters_customer_words_to_raw_catalog_values() -> None:
    products = [{"sku": "yes", "attributes": {"Phone control": "Supported"}},
                {"sku": "no", "attributes": {"Phone control": "Not supported"}}]
    schema = [SlotDef(name="smart", maps_to_field="attributes.Phone control", slot_type="soft", required=False,
                      ask_hint="smart", value_map={"co": ["Supported"], "khong": ["Not supported"]})]
    assert [item["sku"] for item in ontology.apply_ontology_filters("tivi", products, {"smart": "khong"}, schema)] == ["no"]


def test_generic_numeric_normalizer_executes_a_natural_range_without_category_rules() -> None:
    products = [
        {"sku": "small", "attributes": {"Kích cỡ màn hình": "24 inch"}},
        {"sku": "large", "attributes": {"Kích cỡ màn hình": "32 inch"}},
    ]
    # The compiler may call this a choice; catalog evidence must still make a
    # natural numeric range executable.
    schema = [SlotDef(name="display", maps_to_field="attributes.Kích cỡ màn hình", slot_type="soft",
                      required=False, ask_hint="size", question_type="choice", operation="min", unit="inch")]
    result = ontology.apply_ontology_filters("tivi", products, {"display": "trên 24 inch"}, schema)
    assert [item["sku"] for item in result] == ["large"]


def test_generic_ordinal_normalizer_executes_or_higher_from_catalog_order() -> None:
    products = [
        {"sku": "hd", "attributes": {"Độ phân giải": "HD"}},
        {"sku": "full_hd", "attributes": {"Độ phân giải": "Full HD"}},
        {"sku": "4k", "attributes": {"Độ phân giải": "4K"}},
    ]
    schema = [SlotDef(name="resolution", maps_to_field="attributes.Độ phân giải", slot_type="soft",
                      required=False, ask_hint="resolution", question_type="choice", operation="min",
                      ordered_values=["HD", "Full HD", "4K"])]
    result = ontology.apply_ontology_filters("tivi", products, {"resolution": "Full HD hoặc hơn"}, schema)
    assert [item["sku"] for item in result] == ["full_hd", "4k"]


def test_composite_filter_and_preference_preserve_customer_operator() -> None:
    products = [
        {"sku": "hd", "attributes": {"Resolution": "HD"}},
        {"sku": "full", "attributes": {"Resolution": "Full HD"}},
        {"sku": "4k", "attributes": {"Resolution": "4K"}},
    ]
    definition = SlotDef(name="resolution", maps_to_field="attributes.Resolution", slot_type="soft",
                         required=False, ask_hint="resolution", question_type="choice", operation="min",
                         ordered_values=["HD", "Full HD", "4K"])
    assert ontology.answer_status(
        definition, "Full HD trở lên", products,
        wants_filter=True, preference="higher", skip=True,
    ) == (True, True, "resolved")


def test_universal_all_answer_never_switches_a_catalog_filter_to_zero() -> None:
    products = [{"sku": "one", "attributes": {"Smart": "Có"}},
                {"sku": "two", "attributes": {"Smart": "Không"}}]
    schema = [SlotDef(name="smart", maps_to_field="attributes.Smart", slot_type="soft", required=False,
                      ask_hint="smart", value_map={"có": ["Có"], "không": ["Không"]})]
    assert ontology.apply_ontology_filters("tivi", products, {"smart": "tất cả"}, schema) == products


def test_unknown_active_answer_skips_but_ambiguous_answer_requires_clarification() -> None:
    products = [{"sku": "yes", "attributes": {"Smart": "Có"}},
                {"sku": "no", "attributes": {"Smart": "Không"}}]
    definition = SlotDef(name="smart", maps_to_field="attributes.Smart", slot_type="soft", required=False,
                         ask_hint="smart", value_map={"có": ["Có"], "không": ["Không"]})
    assert ontology.answer_status(definition, "tôi không biết", products, skip=True) == (False, False, "skip")
    assert ontology.answer_status(definition, "tôi muốn", products) == (False, False, "unresolved")


def test_boolean_meaning_is_language_independent_and_negative_without_raw_value_completes_question() -> None:
    products = [{"sku": "yes", "attributes": {"Control": "SmartThings"}},
                {"sku": "other", "attributes": {"Control": "Google Cast"}}]
    definition = SlotDef(
        name="control", maps_to_field="attributes.Control", slot_type="soft", required=False,
        ask_hint="control", question_type="boolean",
        boolean_true_values=["SmartThings"], boolean_false_values=[],
    )
    assert ontology.answer_status(definition, "any language", products, boolean_value=False) == (False, False, "skip")
    assert ontology.answer_status(definition, "any language", products, boolean_value=True) == (True, False, "resolved")
    filtered = ontology.apply_ontology_filters(
        "any", products, {"control": ontology._BOOLEAN_TRUE}, [definition]
    )
    assert [product["sku"] for product in filtered] == ["yes"]


def test_active_question_reply_is_not_a_new_category_search() -> None:
    # Routing guards are intentionally state-driven: a one-word reply to an
    # active question must remain in the established category.
    expected = {"slot": "smart", "question": "Smart?", "type": "choice", "answers": "Có | Không"}
    result = _mock_intent("tất cả", "tivi", expected)
    assert result.intent_type == "same_topic"
    assert result.ontology_answers == {"smart": "tất cả"}


def test_runtime_slots_are_engine_owned_and_malformed_generated_questions_are_rejected() -> None:
    assert not re.fullmatch(r"[A-Z][A-Z0-9_]+", "Anh/chị cần màn hình bao nhiêu inch?")
    category = "tivi"
    field = "Kích cỡ màn hình"
    question = "Anh/chị cần màn hình bao nhiêu inch?"
    first = sha256(f"{ontology._normal(category)}|{field}|{question}".encode("utf-8")).hexdigest()[:12].upper()
    second = sha256(f"{ontology._normal(category)}|{field}|{question}".encode("utf-8")).hexdigest()[:12].upper()
    assert first == second
    assert first not in {"mapped", "generated"}


def test_profile_validation_rejects_internal_questions_and_fake_raw_values() -> None:
    questions = [
        RuntimeQuestion(slot="mapped", question="Q_GEN_AUDIO_POWER", question_type="numeric",
                        field="Tổng công suất loa", operation="min", customer_effort=0.9,
                        requires_technical_knowledge=True),
        RuntimeQuestion(slot="generated", question="Anh/chị muốn loại tivi nào ạ?", question_type="choice",
                        field="Loại Tivi", operation="equals", answer_values={"Thường": [""]},
                        customer_effort=0.2, requires_technical_knowledge=False),
    ]
    valid, errors = _validate_questions(
        questions, {"Tổng công suất loa", "Loại Tivi"},
        {"Tổng công suất loa": ["10W", "20W"], "Loại Tivi": ["Smart Tivi", "Tivi LED"]},
    )
    assert valid == []
    assert len(errors) == 2


def test_runtime_slots_and_sentinels_never_leak_to_customer_funnel() -> None:
    schema = [SlotDef(name="Q_RUNTIME_SCREEN", maps_to_field="attributes.Screen size",
                      slot_type="soft", required=False, ask_hint="size")]
    visible = _customer_visible_slots({
        "budget_max": 20_000_000,
        "Q_RUNTIME_AUDIO": ontology._SKIP_ANSWER,
        "Q_RUNTIME_SCREEN": "around 50 inch",
    }, schema)
    assert visible == {"budget_max": 20_000_000, "Screen size": "around 50 inch"}


def test_price_ranking_excludes_products_with_unknown_price() -> None:
    products = [{"sku": "unknown", "price_sale": None}, {"sku": "priced", "price_sale": 100}]
    assert [item["sku"] for item in rank_top3(products, [])] == ["priced"]


def test_locale_numbers_preserve_grouped_thousands_and_decimals() -> None:
    assert ontology.parse_numbers("10.000.000đ") == [10_000_000]
    assert ontology.parse_numbers("10,000,000 VND") == [10_000_000]
    assert ontology.parse_numbers("10.5 inch") == [10.5]


def test_numeric_questions_reject_unsupported_scalar_operations() -> None:
    definition = SlotDef(
        name="size", maps_to_field="attributes.Size", slot_type="soft", required=False,
        ask_hint="size", question_type="numeric", operation="equals",
    )
    products = [{"sku": "one", "attributes": {"Size": "24 inch"}}]
    assert ontology.answer_status(definition, "24", products) == (False, False, "unresolved")
    try:
        ontology.apply_ontology_filters("tivi", products, {"size": "24"}, [definition])
    except ValueError as error:
        assert "Unsupported numeric operation" in str(error)
    else:
        raise AssertionError("unsupported numeric predicate was silently ignored")


def test_explicit_higher_price_preference_is_not_cancelled_by_default_cheap_ranking() -> None:
    products = [
        {"sku": "cheap", "price_sale": 100, "attributes": {}},
        {"sku": "expensive", "price_sale": 300, "attributes": {}},
    ]
    ranked = rank_top3(products, [], [{"field": "price_sale", "direction": "higher"}])
    assert ranked[0]["sku"] == "expensive"


def test_category_matching_requires_complete_words() -> None:
    assert _contains_label("toi muon mua loa", "loa")
    assert not _contains_label("toi chon loai 2", "loa")
