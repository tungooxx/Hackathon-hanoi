# Phased Implementation Plan: Product Catalog Generator

## Summary

Build the generator through small, independently testable phases. First restore the package, then derive strict Pydantic models from the schema, implement a structurally valid seeded generator, improve values category by category, and finally expose the CLI.

Each phase should leave the repository passing its tests before the next phase begins.

## Phase 0 — Restore the Package Skeleton

- Recreate the missing package directory, `__init__.py`, CLI module, models module, and README.
- Keep the existing `synthetic-retail-generator` entry point.
- Add minimal import and CLI smoke tests.
- Do not implement product generation yet.

Completion criteria:

- `uv sync --dev` succeeds.
- `uv run python -c "import synthetic_retail_generator"` succeeds.
- The CLI displays help without errors.
- `uv run pytest` succeeds.

## Phase 1 — Parse and Verify the Source Schema

- Implement a development-time schema reader for `product_catalog_schema_clean.json`.
- Verify:
  - Draft 2020-12 structure.
  - Root `products` array.
  - All 14 referenced definitions exist.
  - All product definitions are objects with `additionalProperties: false`.
  - All declared properties appear in each definition’s `required` list.
- Implement the JSON Schema to Python type mapping:
  - `string` → strict string.
  - `integer` → strict integer.
  - `number` → finite JSON number.
  - Nullable types → required union with `None`.
  - Multi-type properties → union of their declared primitive types.
- Fail with a field-specific error when an unsupported schema construct appears.

Completion criteria:

- Tests confirm 14 definitions, 551 declarations, and 253 unique field names.
- Tests cover every type signature currently present in the schema.
- Malformed or unsupported schema fixtures produce clear errors.

## Phase 2 — Define the Pydantic Product Models

- Create a shared strict base model configured with:
  - `extra="forbid"`.
  - Strict validation.
  - Assignment validation.
- Define one explicit Pydantic class per category, such as `TuLanhProduct`.
- Preserve:
  - Original snake_case property names.
  - Per-category field types.
  - Required nullable fields without default values.
  - Field titles where present.

Completion criteria:

- All 14 classes import successfully.
- Missing required fields, extra fields, and incorrect strict types are rejected.

## Phase 3 — Define the Catalog Model and Public Model API

Add the initial public API:

- `CategoryCode`: enum containing the 14 `$defs` keys.
- `ProductVariant`: union of the 14 product classes.
- `ProductCatalog`: strict model containing `products: list[ProductVariant]`.
- `CATEGORY_MODEL_BY_CODE`: mapping from category code to Pydantic class.
- `CATEGORY_TITLE_BY_CODE`: mapping from category code to Vietnamese schema title.

Generated records will use:

- `category_code` equal to the `$defs` key.
- `category_name` equal to the definition title.

Do not constrain these two fields with `Literal`, because the source schema only declares them as strings.

Completion criteria:

- A catalog can contain every product variant.
- Each generated sample validates against its category model.
- Missing nullable keys are rejected, while explicit `None` is accepted where permitted.
- The public models can be imported from the package root.

## Phase 4 — Implement the Generator Foundation

Create the validated `GenerationConfig`:

```text
count: positive integer = 100
seed: integer = 0
categories: selected category codes = all
category_weights: positive weights = equal
nullable_rate: float from 0 through 1 = 0.15
reference_year: integer = 2026
```

Implement:

- A generation context containing one `random.Random(seed)` instance.
- Deterministic category allocation using normalized weights and largest-remainder rounding.
- Deterministic shuffling of the resulting category schedule.
- Primitive providers for strict strings, integers, numbers, nullable values, and multi-type unions.
- `generate_product(category, index, context)`.
- `generate_catalog(config) -> ProductCatalog`.

This phase may use generic values, but every output must already satisfy the complete schema.

Completion criteria:

- All 14 categories can be generated.
- Requested product count is exact.
- Identical configuration and seed produce identical model dumps.
- Different seeds change generated values.
- Every generated catalog passes Pydantic validation.

## Phase 5 — Implement Shared Product Rules

Replace generic values for fields shared across categories:

- Category code and name.
- Brand and optional brand ID.
- SKU, model code, and web product ID.
- Original price, promotional price, and promotional gift.
- Release year.
- Common dimensions and product weight.
- Common materials, technologies, and utility descriptions.

Enforce cross-field rules:

- Generated identifiers are deterministic and unique within a catalog.
- Original prices are positive and category-appropriate.
- Promotional prices never exceed original prices.
- Promotional descriptions agree with the selected promotion.
- Nullable values are emitted only where the selected category permits them.

Completion criteria:

- No shared identity or pricing field uses a primitive fallback.
- Identifier uniqueness and price invariants are tested.
- Vietnamese strings serialize without escaping or corruption.

## Phase 6 — Add Category-Aware Generation Rules

Implement category-specific profiles incrementally.

### Phase 6A — Large Appliances

Cover:

- Refrigerators.
- Air conditioners.
- Washing machines.
- Clothes dryers.
- Dishwashers.
- Coolers/freezers.
- Water heaters.

Add plausible ranges and values for capacities, power consumption, dimensions, motors, cooling/washing technologies, programs, and installation specifications.

### Phase 6B — Audio and Wearables

Cover:

- Karaoke microphones.
- Mobile recording microphones.
- Smartwatches.

Add plausible battery, charging, frequency, connectivity, microphone, display, sensor, and wearable specifications.

### Phase 6C — Computing Products

Cover:

- Desktop computers.
- Computer monitors.
- Printers.
- Tablets.

Add plausible CPU, RAM, storage, GPU, display, connectivity, printing, operating-system, camera, and battery specifications.

For every category, provider precedence will be:

1. Category-and-field rule.
2. Shared exact-field rule.
3. Semantic field rule.
4. Explicitly approved generic fallback.

Completion criteria for each subphase:

- Every field in the covered categories resolves to a named provider.
- Generated values satisfy the declared field types.
- Numeric specifications stay within documented category ranges.
- At least 100 generated examples per category pass Pydantic and source-schema validation.

## Phase 7 — Add Independent Schema Validation

- Add `jsonschema` as a development-only dependency.
- Validate the source schema with `Draft202012Validator.check_schema`.
- Validate every category sample against its direct `$defs` definition.
- Validate complete `{"products": [...]}` output against the root schema.
- Add a provider-coverage test so schema fields cannot silently fall back to meaningless values.

Completion criteria:

- Pydantic and the original JSON Schema both accept generated catalogs.
- Model/schema parity and provider-coverage tests fail when the schema changes without corresponding implementation updates.

## Phase 8 — Implement JSON Output and CLI

Implement CLI arguments:

```text
--count INTEGER
--seed INTEGER
--category CATEGORY_CODE
--category-weight CATEGORY_CODE=FLOAT
--nullable-rate FLOAT
--reference-year INTEGER
--output PATH
```

Behavior:

- Repeated `--category` values restrict generation; all categories are used by default.
- Unspecified selected categories receive weight `1.0`.
- Default output path is `product_catalog.json`.
- Serialize exactly `{"products": [...]}` using Pydantic JSON mode.
- Write UTF-8 JSON with readable Vietnamese characters.
- Validate the complete catalog before writing.
- Use an atomic temporary-file replacement to avoid partial output.
- Return concise errors and nonzero exit codes for invalid arguments, generation failures, or filesystem errors.

Completion criteria:

- A default CLI invocation generates 100 valid products.
- Category filtering and weighting work as documented.
- Invalid count, weight, nullable rate, category, or path is rejected.
- Running the same command twice produces byte-identical JSON.
- End-to-end output validates against the source schema.

## Phase 9 — Documentation and Final Verification

- Document installation, library usage, CLI examples, category codes, defaults, reproducibility, and schema regeneration.
- Explain that nullable fields remain present with `null`.
- Document how to add a new category or field:
  1. Update the source schema.
  2. Update the corresponding Pydantic model.
  3. Add or approve value providers.
  4. Run drift, coverage, and validation tests.
- Run:
  - `uv sync --dev`
  - model/schema parity checks
  - `uv run pytest`
  - package build
  - end-to-end CLI generation and schema validation

## Deferred Work

The following remain outside the product-generator MVP:

- Users, sessions, events, orders, and order items.
- Duplicate, skew, or deliberately invalid anomaly injection.
- JSON Lines, CSV, and Parquet export.
- Runtime dynamic model creation.
- Reading the schema during normal catalog generation.

The model registry, seeded generation context, and serialization boundary should remain modular so these features can be added without changing the product contract.
