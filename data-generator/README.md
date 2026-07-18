# Synthetic Retail Data Generator

Generate reproducible synthetic retail product catalogs from the structural
contract in `docs/product_catalog_schema_clean.json`.

The generator uses strict Pydantic models for all 14 product categories and
writes a single schema-shaped JSON document.

## Generate data

```powershell
uv run synthetic-retail-generator --count 100 --seed 42 --output product_catalog.json
```

Limit generation to selected categories by repeating `--category`:

```powershell
uv run synthetic-retail-generator --count 20 `
  --category tu_lanh `
  --category may_lanh `
  --output appliances.json
```

The same arguments and seed produce the same JSON data.

## Development

```powershell
uv sync --dev
uv run pytest
```
