"""Quick dirty-catalog regression test. Run: python scripts/test_catalog_normalizer.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog_normalizer import normalize_products


fixture = Path(__file__).resolve().parent.parent / "fixtures" / "may_lanh.json"
products = normalize_products(json.loads(fixture.read_text(encoding="utf-8")), "may_lanh")

assert products[0]["price_sale"] == 8_500_000
assert products[0]["area_min_m2"] == 0 and products[0]["area_max_m2"] == 15
assert products[0]["noise_db_min"] == 27.5 and products[0]["energy_stars"] == 5
assert products[1]["area_min_m2"] == 20 and products[1]["area_max_m2"] == 30
assert products[2]["_evidence"]["area"] == "UNKNOWN"
print("PASS: dirty catalog normalized without inventing missing facts")
