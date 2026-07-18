"""Command-line entry point for the synthetic retail generator."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from synthetic_retail_generator.generator import (
    GenerationConfig,
    generate_catalog,
    write_catalog,
)
from synthetic_retail_generator.models import CategoryCode


def build_parser() -> argparse.ArgumentParser:
    """Build the product-generation CLI parser."""

    parser = argparse.ArgumentParser(
        description="Generate a synthetic retail product catalog."
    )
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--category",
        action="append",
        choices=[category.value for category in CategoryCode],
        help="Limit output to a category; may be repeated.",
    )
    parser.add_argument("--nullable-rate", type=float, default=0.15)
    parser.add_argument("--reference-year", type=int, default=2026)
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
    categories = (
        tuple(CategoryCode(value) for value in args.category)
        if args.category
        else tuple(CategoryCode)
    )
    try:
        config = GenerationConfig(
            count=args.count,
            seed=args.seed,
            categories=categories,
            nullable_rate=args.nullable_rate,
            reference_year=args.reference_year,
        )
        catalog = generate_catalog(config)
        output_path = write_catalog(catalog, args.output)
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(str(exc))

    print(f"Generated {len(catalog.products)} products: {output_path}")
    return 0
