"""Synthetic retail product catalog generator."""

from synthetic_retail_generator.generator import (
    GenerationConfig,
    catalog_to_json,
    generate_catalog,
    generate_product,
    write_catalog,
)
from synthetic_retail_generator.models import (
    CATEGORY_MODEL_BY_CODE,
    CATEGORY_TITLE_BY_CODE,
    CategoryCode,
    ProductCatalog,
    ProductModel,
    ProductVariant,
)
from synthetic_retail_generator.schema_reader import (
    ProductCatalogSchema,
    ProductDefinitionSpec,
    PropertySpec,
    SchemaContractError,
    SchemaLoadError,
    TypeMapping,
    load_product_catalog_schema,
    map_json_schema_type,
    parse_product_catalog_schema,
)

__all__ = [
    "CATEGORY_MODEL_BY_CODE",
    "CATEGORY_TITLE_BY_CODE",
    "CategoryCode",
    "GenerationConfig",
    "ProductCatalog",
    "ProductCatalogSchema",
    "ProductDefinitionSpec",
    "ProductModel",
    "ProductVariant",
    "PropertySpec",
    "SchemaContractError",
    "SchemaLoadError",
    "TypeMapping",
    "catalog_to_json",
    "generate_catalog",
    "generate_product",
    "load_product_catalog_schema",
    "map_json_schema_type",
    "parse_product_catalog_schema",
    "write_catalog",
]
