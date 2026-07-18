from __future__ import annotations

import json

from synthetic_retail_generator.cli import main
from synthetic_retail_generator.generator import (
    GenerationConfig,
    catalog_to_json,
    generate_catalog,
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


def test_cli_writes_json_catalog(tmp_path) -> None:
    output = tmp_path / "catalog.json"

    assert main(["--count", "3", "--seed", "7", "--output", str(output)]) == 0

    document = json.loads(output.read_text(encoding="utf-8"))
    assert len(document["products"]) == 3
    ProductCatalog.model_validate(document)
