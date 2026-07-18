from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_retail_generator.schema_reader import (
    SchemaContractError,
    load_product_catalog_schema,
    parse_product_catalog_schema,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "product_catalog_schema_clean.json"
)


def test_catalog_schema_inventory_and_type_signatures() -> None:
    schema = load_product_catalog_schema(SCHEMA_PATH)

    assert len(schema.definitions) == 14
    assert schema.total_property_declarations == 551
    assert len(schema.unique_property_names) == 253
    assert schema.type_signatures == {
        "string",
        "string|null",
        "integer",
        "integer|null",
        "integer|string",
        "integer|string|null",
        "number|string",
    }


def test_unsupported_field_type_reports_its_location() -> None:
    document = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    document["$defs"]["tu_lanh"]["properties"]["sku"]["type"] = "boolean"

    with pytest.raises(SchemaContractError) as raised:
        parse_product_catalog_schema(document)

    message = str(raised.value)
    assert "$.$defs.tu_lanh.properties.sku.type" in message
    assert "boolean" in message
