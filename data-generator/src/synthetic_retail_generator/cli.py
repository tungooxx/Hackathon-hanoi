"""Command-line entry point for the synthetic retail generator."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from synthetic_retail_generator.generator import (
    DEFAULT_CONFIG_PATH,
    GenerationConfig,
    generate_catalog,
    load_generation_config,
    write_catalog,
)
from synthetic_retail_generator.models import CategoryCode


def _category_weight(value: str) -> tuple[CategoryCode, float]:
    category_text, separator, weight_text = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("expected CATEGORY=WEIGHT")
    try:
        category = CategoryCode(category_text)
        weight = float(weight_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return category, weight


def build_parser() -> argparse.ArgumentParser:
    """Build the product-generation CLI parser."""

    parser = argparse.ArgumentParser(
        description="Generate a synthetic retail product catalog."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="YAML generation config (default: configs/data-issue.yaml).",
    )
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--category",
        action="append",
        choices=[category.value for category in CategoryCode],
        help="Limit output to a category; may be repeated.",
    )
    parser.add_argument("--nullable-rate", type=float)
    parser.add_argument("--reference-year", type=int)
    parser.add_argument(
        "--category-weight",
        action="append",
        type=_category_weight,
        default=[],
        metavar="CATEGORY=WEIGHT",
        help="Set a positive generation weight; may be repeated.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("product_catalog.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate and write a product catalog."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        base_config = load_generation_config(args.config)
        values = base_config.model_dump()

        for name in ("count", "seed", "nullable_rate", "reference_year"):
            value = getattr(args, name)
            if value is not None:
                values[name] = value

        categories = base_config.categories
        if args.category:
            categories = tuple(CategoryCode(value) for value in args.category)
            values["categories"] = categories

        category_weights = {
            category: weight
            for category, weight in base_config.category_weights.items()
            if category in categories
        }
        cli_weight_categories: set[CategoryCode] = set()
        for category, weight in args.category_weight:
            if category in cli_weight_categories:
                parser.error(f"duplicate category weight: {category.value}")
            cli_weight_categories.add(category)
            category_weights[category] = weight
        values["category_weights"] = category_weights

        config = GenerationConfig.model_validate(values)
        catalog = generate_catalog(config)
        output_path = write_catalog(catalog, args.output)
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(str(exc))

    print(f"Generated {len(catalog.products)} products: {output_path}")
    return 0
