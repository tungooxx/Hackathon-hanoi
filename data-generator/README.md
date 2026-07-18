# Synthetic Retail Data Generator

Generate reproducible synthetic retail product catalogs from the structural
contract in `docs/product_catalog_schema_clean.json`.

The generator uses strict Pydantic models for all 14 product categories and
writes a single schema-shaped JSON document.

Generation settings are read from `configs/data-issue.yaml` by default.

## Generate data

```powershell
uv run synthetic-retail-generator --output product_catalog.json
```

Edit `configs/data-issue.yaml` to change the product count, seed, selected
categories, category weights, nullable rate, or reference year. CLI options
override the corresponding YAML settings:

```powershell
uv run synthetic-retail-generator --count 20 `
  --category tu_lanh `
  --category may_lanh `
  --output appliances.json
```

Use another configuration file with `--config path/to/config.yaml`.

The same arguments and seed produce the same JSON data.

## Development

```powershell
uv sync --dev
uv run pytest
```
