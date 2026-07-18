from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adaptive_ontology import AdaptCategoryRequest, AdaptiveOntologyEngine, NextQuestionRequest


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
    assert all("transfer_mode" in item for item in first.relationships)
