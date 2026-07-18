from __future__ import annotations

import json

from synthetic_retail_generator.cli import main
from synthetic_retail_generator.generator import (
    GenerationConfig,
    _CATEGORY_PROFILES,
    _MATERIALS,
    _NO_PROMOTION_DESCRIPTION,
    _RELEASE_YEAR_FIELDS,
    _TECHNOLOGIES,
    _UTILITIES,
    _UTILITY_FIELDS,
    _is_dimension_field,
    allocate_category_counts,
    catalog_to_json,
    generate_catalog,
    load_generation_config,
)
from synthetic_retail_generator.models import (
    CATEGORY_MODEL_BY_CODE,
    CategoryCode,
    ProductCatalog,
)


def test_generation_is_valid_balanced_and_reproducible() -> None:
    config = GenerationConfig(
        count=len(CategoryCode),
        seed=42,
        nullable_rate=0.25,
    )

    first = generate_catalog(config)
    second = generate_catalog(config)

    assert len(first.products) == len(CategoryCode)
    assert {type(product) for product in first.products} == set(
        CATEGORY_MODEL_BY_CODE.values()
    )
    assert catalog_to_json(first) == catalog_to_json(second)
    ProductCatalog.model_validate(json.loads(catalog_to_json(first)))
    assert catalog_to_json(first) != catalog_to_json(
        generate_catalog(config.model_copy(update={"seed": 43}))
    )


def test_weighted_allocation_uses_largest_remainders() -> None:
    categories = (
        CategoryCode.TU_LANH,
        CategoryCode.MAY_LANH,
        CategoryCode.MAY_GIAT,
    )
    config = GenerationConfig(
        count=10,
        seed=1,
        categories=categories,
        category_weights={
            CategoryCode.TU_LANH: 2.0,
            CategoryCode.MAY_LANH: 1.0,
            CategoryCode.MAY_GIAT: 1.0,
        },
    )

    assert allocate_category_counts(config) == {
        CategoryCode.TU_LANH: 5,
        CategoryCode.MAY_LANH: 3,
        CategoryCode.MAY_GIAT: 2,
    }
    catalog = generate_catalog(config)
    generated_counts = {
        category: sum(
            product.category_code == category.value
            for product in catalog.products
        )
        for category in categories
    }
    assert generated_counts == allocate_category_counts(config)


def test_load_generation_config_from_yaml(tmp_path) -> None:
    config_path = tmp_path / "data-issue.yaml"
    config_path.write_text(
        "\n".join(
            (
                "count: 3",
                "seed: 17",
                "categories:",
                "  - tu_lanh",
                "  - may_lanh",
                "category_weights:",
                "  tu_lanh: 2.0",
                "nullable_rate: 0.25",
                "reference_year: 2025",
            )
        ),
        encoding="utf-8",
    )

    config = load_generation_config(config_path)

    assert config.count == 3
    assert config.seed == 17
    assert config.categories == (
        CategoryCode.TU_LANH,
        CategoryCode.MAY_LANH,
    )
    assert config.category_weights == {CategoryCode.TU_LANH: 2.0}
    assert config.nullable_rate == 0.25
    assert config.reference_year == 2025


def test_shared_identity_and_pricing_rules() -> None:
    catalog = generate_catalog(
        GenerationConfig(
            count=280,
            seed=2026,
            nullable_rate=0.5,
        )
    )

    assert len({product.sku for product in catalog.products}) == 280
    assert len({product.model_code for product in catalog.products}) == 280
    assert len({product.productidweb for product in catalog.products}) == 280

    for product in catalog.products:
        category = CategoryCode(product.category_code)
        profile = _CATEGORY_PROFILES[category]
        price_low, price_high = profile.price_range

        assert product.category_name == CATEGORY_MODEL_BY_CODE[
            category
        ].model_config["title"]
        assert product.brand in profile.brands
        if hasattr(product, "brand_id"):
            assert product.brand_id == (
                f"brand-{product.brand.casefold().replace(' ', '-')}"
            )
        assert price_low <= product.gia_goc <= price_high

        if product.gia_khuyen_mai is None:
            assert product.khuyen_mai_qua in {
                None,
                _NO_PROMOTION_DESCRIPTION,
            }
        else:
            assert 0 < product.gia_khuyen_mai < product.gia_goc
            assert product.khuyen_mai_qua is not None
            assert product.khuyen_mai_qua.startswith("Giảm ")


def test_shared_semantic_fields_use_named_providers() -> None:
    reference_year = 2026
    catalog = generate_catalog(
        GenerationConfig(
            count=140,
            seed=51,
            nullable_rate=0.25,
            reference_year=reference_year,
        )
    )

    for product in catalog.products:
        for name, value in product.model_dump().items():
            if value is None:
                continue
            if name in _RELEASE_YEAR_FIELDS:
                assert reference_year - 8 <= int(value) <= reference_year
            elif _is_dimension_field(name):
                assert isinstance(value, int | float) and value > 0 or (
                    isinstance(value, str)
                    and value.endswith((" mm", " inch"))
                )
            elif "khoi_luong" in name:
                assert isinstance(value, int | float) and value > 0 or (
                    isinstance(value, str) and value.endswith(" kg")
                )
            elif "chat_lieu" in name:
                assert value in _MATERIALS
            elif "cong_nghe" in name:
                assert value in _TECHNOLOGIES
            elif name in _UTILITY_FIELDS or name.startswith("tinh_nang_"):
                assert value in _UTILITIES


def test_catalog_json_preserves_vietnamese_text() -> None:
    catalog = generate_catalog(
        GenerationConfig(
            count=1,
            seed=3,
            categories=(CategoryCode.TU_LANH,),
            nullable_rate=0.0,
        )
    )

    json_text = catalog_to_json(catalog)

    assert "Tủ Lạnh" in json_text
    assert any(material in json_text for material in _MATERIALS)
    assert "\\u" not in json_text
    assert json_text.encode("utf-8").decode("utf-8") == json_text


def test_cli_writes_json_catalog(tmp_path) -> None:
    output = tmp_path / "catalog.json"

    assert main(["--count", "3", "--seed", "7", "--output", str(output)]) == 0

    document = json.loads(output.read_text(encoding="utf-8"))
    assert len(document["products"]) == 3
    ProductCatalog.model_validate(document)


def test_cli_uses_yaml_config(tmp_path) -> None:
    config_path = tmp_path / "data-issue.yaml"
    output = tmp_path / "catalog.json"
    config_path.write_text(
        "\n".join(
            (
                "count: 2",
                "seed: 9",
                "categories: [may_in]",
                "category_weights: {}",
                "nullable_rate: 0.1",
                "reference_year: 2026",
            )
        ),
        encoding="utf-8",
    )

    assert main(["--config", str(config_path), "--output", str(output)]) == 0

    document = json.loads(output.read_text(encoding="utf-8"))
    assert len(document["products"]) == 2
    assert {
        product["category_code"] for product in document["products"]
    } == {CategoryCode.MAY_IN.value}
