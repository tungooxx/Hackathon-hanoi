"""Read and verify the structural product catalog JSON Schema.

This module deliberately supports only the schema constructs used by the
catalog contract. Unsupported constructs fail early so the model-generation
phase cannot silently discard validation behavior.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias

JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

JsonPrimitiveType: TypeAlias = Literal["string", "integer", "number", "null"]
JsonObject: TypeAlias = Mapping[str, Any]

_TYPE_ANNOTATIONS: dict[JsonPrimitiveType, str] = {
    "integer": "StrictInt",
    "number": "FiniteNumber",
    "string": "StrictStr",
    "null": "None",
}
_TYPE_ORDER: tuple[JsonPrimitiveType, ...] = (
    "integer",
    "number",
    "string",
    "null",
)
_SUPPORTED_PROPERTY_KEYWORDS = frozenset({"description", "title", "type"})


class SchemaLoadError(RuntimeError):
    """Raised when the schema file cannot be read or decoded."""


class SchemaContractError(ValueError):
    """Raised when the schema uses an invalid or unsupported structure."""


@dataclass(frozen=True, slots=True)
class TypeMapping:
    """Normalized JSON primitive types and their Pydantic annotation source."""

    json_types: tuple[JsonPrimitiveType, ...]
    python_annotation: str

    @property
    def nullable(self) -> bool:
        return "null" in self.json_types

    @property
    def signature(self) -> str:
        return "|".join(self.json_types)


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """A required property declared by one product definition."""

    name: str
    title: str | None
    type_mapping: TypeMapping


@dataclass(frozen=True, slots=True)
class ProductDefinitionSpec:
    """One product category definition from ``$defs``."""

    key: str
    title: str
    properties: tuple[PropertySpec, ...]


@dataclass(frozen=True, slots=True)
class ProductCatalogSchema:
    """Verified schema information needed by model generation."""

    source: str
    schema_id: str | None
    definitions: tuple[ProductDefinitionSpec, ...]

    @property
    def total_property_declarations(self) -> int:
        return sum(len(definition.properties) for definition in self.definitions)

    @property
    def unique_property_names(self) -> frozenset[str]:
        return frozenset(
            prop.name
            for definition in self.definitions
            for prop in definition.properties
        )

    @property
    def type_signatures(self) -> frozenset[str]:
        return frozenset(
            prop.type_mapping.signature
            for definition in self.definitions
            for prop in definition.properties
        )


def _contract_error(source: str, location: str, message: str) -> SchemaContractError:
    return SchemaContractError(f"{source}:{location}: {message}")


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def map_json_schema_type(
    schema_type: object,
    *,
    source: str = "<schema>",
    location: str = "$",
) -> TypeMapping:
    """Map a JSON Schema primitive type declaration to Pydantic type names."""

    if isinstance(schema_type, str):
        declared_types: tuple[object, ...] = (schema_type,)
    elif _is_sequence(schema_type):
        declared_types = tuple(schema_type)
    else:
        raise _contract_error(
            source,
            location,
            "'type' must be a string or a non-empty array of strings",
        )

    if not declared_types:
        raise _contract_error(source, location, "'type' array cannot be empty")
    if any(not isinstance(item, str) for item in declared_types):
        raise _contract_error(source, location, "every declared type must be a string")
    if len(set(declared_types)) != len(declared_types):
        raise _contract_error(source, location, "'type' contains duplicate values")

    unsupported = sorted(set(declared_types) - set(_TYPE_ANNOTATIONS))
    if unsupported:
        raise _contract_error(
            source,
            location,
            f"unsupported JSON Schema type(s): {', '.join(unsupported)}",
        )

    normalized = tuple(
        json_type for json_type in _TYPE_ORDER if json_type in declared_types
    )
    if normalized == ("null",):
        raise _contract_error(
            source,
            location,
            "a property cannot declare only the null type",
        )

    return TypeMapping(
        json_types=normalized,
        python_annotation=" | ".join(
            _TYPE_ANNOTATIONS[json_type] for json_type in normalized
        ),
    )


def _require_mapping(
    value: object,
    *,
    source: str,
    location: str,
) -> JsonObject:
    if not isinstance(value, Mapping):
        raise _contract_error(source, location, "must be an object")
    return value


def _require_string(
    value: object,
    *,
    source: str,
    location: str,
) -> str:
    if not isinstance(value, str) or not value:
        raise _contract_error(source, location, "must be a non-empty string")
    return value


def _require_string_sequence(
    value: object,
    *,
    source: str,
    location: str,
) -> tuple[str, ...]:
    if not _is_sequence(value) or any(not isinstance(item, str) for item in value):
        raise _contract_error(source, location, "must be an array of strings")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise _contract_error(source, location, "must not contain duplicate values")
    return result


def _parse_definition(
    key: str,
    raw_definition: object,
    *,
    source: str,
) -> ProductDefinitionSpec:
    location = f"$.$defs.{key}"
    definition = _require_mapping(
        raw_definition,
        source=source,
        location=location,
    )
    if definition.get("type") != "object":
        raise _contract_error(source, f"{location}.type", "must equal 'object'")
    if definition.get("additionalProperties") is not False:
        raise _contract_error(
            source,
            f"{location}.additionalProperties",
            "must equal false",
        )

    title = _require_string(
        definition.get("title"),
        source=source,
        location=f"{location}.title",
    )
    raw_properties = _require_mapping(
        definition.get("properties"),
        source=source,
        location=f"{location}.properties",
    )
    required = _require_string_sequence(
        definition.get("required"),
        source=source,
        location=f"{location}.required",
    )

    property_names = set(raw_properties)
    required_names = set(required)
    missing_required = sorted(property_names - required_names)
    unknown_required = sorted(required_names - property_names)
    if missing_required:
        raise _contract_error(
            source,
            f"{location}.required",
            f"properties are not required: {', '.join(missing_required)}",
        )
    if unknown_required:
        raise _contract_error(
            source,
            f"{location}.required",
            f"unknown required properties: {', '.join(unknown_required)}",
        )

    properties: list[PropertySpec] = []
    for name, raw_property in raw_properties.items():
        property_location = f"{location}.properties.{name}"
        property_schema = _require_mapping(
            raw_property,
            source=source,
            location=property_location,
        )
        unsupported_keywords = sorted(
            set(property_schema) - _SUPPORTED_PROPERTY_KEYWORDS
        )
        if unsupported_keywords:
            raise _contract_error(
                source,
                property_location,
                "unsupported property keyword(s): "
                + ", ".join(unsupported_keywords),
            )

        raw_title = property_schema.get("title")
        if raw_title is not None and not isinstance(raw_title, str):
            raise _contract_error(
                source,
                f"{property_location}.title",
                "must be a string",
            )
        properties.append(
            PropertySpec(
                name=name,
                title=raw_title,
                type_mapping=map_json_schema_type(
                    property_schema.get("type"),
                    source=source,
                    location=f"{property_location}.type",
                ),
            )
        )

    return ProductDefinitionSpec(
        key=key,
        title=title,
        properties=tuple(properties),
    )


def parse_product_catalog_schema(
    document: object,
    *,
    source: str = "<schema>",
) -> ProductCatalogSchema:
    """Verify and normalize an already-decoded product catalog schema."""

    root = _require_mapping(document, source=source, location="$")
    if root.get("$schema") != JSON_SCHEMA_DRAFT_2020_12:
        raise _contract_error(
            source,
            "$.$schema",
            f"must equal {JSON_SCHEMA_DRAFT_2020_12!r}",
        )
    if root.get("type") != "object":
        raise _contract_error(source, "$.type", "must equal 'object'")
    if root.get("additionalProperties") is not False:
        raise _contract_error(
            source,
            "$.additionalProperties",
            "must equal false",
        )

    root_required = _require_string_sequence(
        root.get("required"),
        source=source,
        location="$.required",
    )
    if "products" not in root_required:
        raise _contract_error(source, "$.required", "must include 'products'")

    root_properties = _require_mapping(
        root.get("properties"),
        source=source,
        location="$.properties",
    )
    products = _require_mapping(
        root_properties.get("products"),
        source=source,
        location="$.properties.products",
    )
    if products.get("type") != "array":
        raise _contract_error(
            source,
            "$.properties.products.type",
            "must equal 'array'",
        )
    items = _require_mapping(
        products.get("items"),
        source=source,
        location="$.properties.products.items",
    )
    raw_variants = items.get("anyOf")
    if not _is_sequence(raw_variants) or not raw_variants:
        raise _contract_error(
            source,
            "$.properties.products.items.anyOf",
            "must be a non-empty array",
        )

    definitions = _require_mapping(
        root.get("$defs"),
        source=source,
        location="$.$defs",
    )
    referenced_keys: list[str] = []
    for index, raw_variant in enumerate(raw_variants):
        variant_location = f"$.properties.products.items.anyOf[{index}]"
        variant = _require_mapping(
            raw_variant,
            source=source,
            location=variant_location,
        )
        reference = _require_string(
            variant.get("$ref"),
            source=source,
            location=f"{variant_location}.$ref",
        )
        prefix = "#/$defs/"
        if not reference.startswith(prefix) or len(reference) == len(prefix):
            raise _contract_error(
                source,
                f"{variant_location}.$ref",
                "must be a local reference under '#/$defs/'",
            )
        referenced_keys.append(reference.removeprefix(prefix))

    if len(referenced_keys) != len(set(referenced_keys)):
        raise _contract_error(
            source,
            "$.properties.products.items.anyOf",
            "contains duplicate product references",
        )

    missing_definitions = sorted(set(referenced_keys) - set(definitions))
    if missing_definitions:
        raise _contract_error(
            source,
            "$.$defs",
            f"missing referenced definitions: {', '.join(missing_definitions)}",
        )
    unreferenced_definitions = sorted(set(definitions) - set(referenced_keys))
    if unreferenced_definitions:
        raise _contract_error(
            source,
            "$.$defs",
            f"contains unreferenced definitions: {', '.join(unreferenced_definitions)}",
        )

    parsed_definitions = tuple(
        _parse_definition(key, definitions[key], source=source)
        for key in referenced_keys
    )
    raw_schema_id = root.get("$id")
    if raw_schema_id is not None and not isinstance(raw_schema_id, str):
        raise _contract_error(source, "$.$id", "must be a string")

    return ProductCatalogSchema(
        source=source,
        schema_id=raw_schema_id,
        definitions=parsed_definitions,
    )


def load_product_catalog_schema(path: str | Path) -> ProductCatalogSchema:
    """Read, decode, verify, and normalize a product catalog schema file."""

    schema_path = Path(path)
    try:
        document = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaLoadError(f"Unable to load schema {schema_path}: {exc}") from exc
    return parse_product_catalog_schema(document, source=str(schema_path))
