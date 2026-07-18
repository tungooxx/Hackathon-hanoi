"""Generate reproducible product catalog JSON data."""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from synthetic_retail_generator.models import (
    CATEGORY_MODEL_BY_CODE,
    CATEGORY_TITLE_BY_CODE,
    CategoryCode,
    ProductCatalog,
    ProductModel,
)

PositiveCount = Annotated[int, Field(gt=0, strict=True)]
Probability = Annotated[
    float,
    Field(ge=0, le=1, allow_inf_nan=False),
]


class GenerationConfig(BaseModel):
    """Validated inputs for deterministic catalog generation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    count: PositiveCount = 100
    seed: int = 0
    categories: tuple[CategoryCode, ...] = tuple(CategoryCode)
    nullable_rate: Probability = 0.15
    reference_year: Annotated[int, Field(ge=2000, le=2100, strict=True)] = 2026

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        categories: tuple[CategoryCode, ...],
    ) -> tuple[CategoryCode, ...]:
        if not categories:
            raise ValueError("at least one category is required")
        if len(categories) != len(set(categories)):
            raise ValueError("categories must not contain duplicates")
        return categories


_CATEGORY_PROFILES: dict[
    CategoryCode,
    tuple[str, tuple[str, ...], tuple[int, int]],
] = {
    CategoryCode.TU_LANH: ("TL", ("Samsung", "LG", "Panasonic"), (5_000_000, 45_000_000)),
    CategoryCode.MAY_LANH: ("ML", ("Daikin", "Panasonic", "LG"), (6_000_000, 35_000_000)),
    CategoryCode.MAY_GIAT: ("MG", ("LG", "Samsung", "Electrolux"), (5_000_000, 30_000_000)),
    CategoryCode.MAY_SAY_QUAN_AO: ("MS", ("Electrolux", "LG", "Bosch"), (8_000_000, 35_000_000)),
    CategoryCode.MAY_RUA_CHEN: ("RC", ("Bosch", "Electrolux", "Hafele"), (9_000_000, 45_000_000)),
    CategoryCode.TU_MAT_TU_DONG: ("TD", ("Sanaky", "Alaska", "Aqua"), (5_000_000, 35_000_000)),
    CategoryCode.MAY_NUOC_NONG: ("NN", ("Ariston", "Ferroli", "Panasonic"), (2_000_000, 15_000_000)),
    CategoryCode.MICRO_KARAOKE: ("MK", ("JBL", "Paramax", "Shure"), (1_000_000, 12_000_000)),
    CategoryCode.MICRO_THU_AM_DIEN_THOAI: ("MT", ("Rode", "DJI", "Boya"), (800_000, 12_000_000)),
    CategoryCode.DONG_HO_THONG_MINH: ("DH", ("Apple", "Samsung", "Garmin"), (2_000_000, 25_000_000)),
    CategoryCode.MAY_TINH_DE_BAN: ("PC", ("Asus", "Dell", "HP"), (8_000_000, 60_000_000)),
    CategoryCode.MAN_HINH_MAY_TINH: ("MH", ("LG", "Dell", "Asus"), (2_000_000, 25_000_000)),
    CategoryCode.MAY_IN: ("MI", ("Canon", "Brother", "HP"), (2_000_000, 20_000_000)),
    CategoryCode.MAY_TINH_BANG: ("TB", ("Apple", "Samsung", "Xiaomi"), (4_000_000, 35_000_000)),
}

_COUNTRIES = ("Việt Nam", "Thái Lan", "Trung Quốc", "Malaysia", "Hàn Quốc")
_MATERIALS = ("Thép không gỉ", "Nhựa ABS", "Hợp kim nhôm", "Kính cường lực")
_TECHNOLOGIES = (
    "Inverter tiết kiệm điện",
    "Điều khiển thông minh",
    "Cảm biến tự động",
    "Khử khuẩn tiên tiến",
)
_CONNECTIONS = ("Bluetooth 5.3", "Wi-Fi", "USB-C", "HDMI")
_PROTECTED_NULL_FIELDS = frozenset(
    {
        "brand",
        "brand_id",
        "category_code",
        "category_name",
        "gia_goc",
        "model_code",
        "productidweb",
        "sku",
    }
)


@lru_cache(maxsize=None)
def _model_properties(model: type[ProductModel]) -> dict[str, dict[str, Any]]:
    return model.model_json_schema()["properties"]


def _json_types(field_schema: dict[str, Any]) -> tuple[str, ...]:
    raw_type = field_schema.get("type")
    if isinstance(raw_type, str):
        return (raw_type,)
    return tuple(
        option["type"]
        for option in field_schema.get("anyOf", ())
        if isinstance(option, dict) and isinstance(option.get("type"), str)
    )


def _rounded_price(rng: random.Random, low: int, high: int) -> int:
    return rng.randrange(low // 10_000, high // 10_000 + 1) * 10_000


def _integer_value(name: str, rng: random.Random, reference_year: int) -> int:
    if name in {"nam_san_xuat", "thoi_gian_ra_mat"}:
        return rng.randint(max(2015, reference_year - 8), reference_year)
    if name.startswith(("cao", "dai", "ngang", "rong", "sau", "day", "do_day")):
        return rng.randint(10, 2_000)
    if "khoi_luong" in name:
        return rng.randint(1, 150)
    if "dung_luong" in name or "dung_tich" in name:
        return rng.randint(10, 1_000)
    if "cong_suat" in name or "dien_nang" in name:
        return rng.randint(50, 3_000)
    if name.startswith("so_") or "so_luong" in name:
        return rng.randint(1, 12)
    return rng.randint(1, 1_000)


def _string_value(
    name: str,
    title: str,
    rng: random.Random,
    reference_year: int,
) -> str:
    if name == "san_xuat_tai":
        return rng.choice(_COUNTRIES)
    if name == "thoi_gian_ra_mat":
        return str(rng.randint(max(2015, reference_year - 8), reference_year))
    if "chat_lieu" in name:
        return rng.choice(_MATERIALS)
    if "cong_nghe" in name or name in {"tien_ich", "tinh_nang_dac_biet"}:
        return rng.choice(_TECHNOLOGIES)
    if name in {"ket_noi", "cong_ket_noi", "cong_giao_tiep", "wifi", "bluetooth"}:
        return rng.choice(_CONNECTIONS)
    if "dung_luong_pin" in name:
        return f"{rng.randrange(1_000, 10_001, 100)} mAh"
    if "dung_tich" in name:
        return f"{rng.randint(10, 700)} lít"
    if "khoi_luong" in name:
        return f"{rng.randint(1, 100)} kg"
    if name.startswith(("cao", "dai", "ngang", "rong", "sau", "day", "do_day")):
        return f"{rng.randint(1, 200)} cm"
    if "cong_suat" in name or "dien_nang" in name:
        return f"{rng.randint(50, 3_000)} W"
    if name.startswith("so_") or "so_luong" in name:
        return str(rng.randint(1, 12))
    if name.startswith("loai_"):
        return rng.choice(("Tiêu chuẩn", "Cao cấp", "Thông minh"))
    return f"{title} {rng.randint(1, 99)}"


def _field_value(
    name: str,
    field_schema: dict[str, Any],
    *,
    rng: random.Random,
    nullable_rate: float,
    reference_year: int,
) -> object:
    allowed_types = _json_types(field_schema)
    if (
        "null" in allowed_types
        and name not in _PROTECTED_NULL_FIELDS
        and rng.random() < nullable_rate
    ):
        return None

    usable_types = tuple(value for value in allowed_types if value != "null")
    if "integer" in usable_types and (
        "string" not in usable_types or rng.random() < 0.5
    ):
        return _integer_value(name, rng, reference_year)
    if "number" in usable_types and (
        "string" not in usable_types or rng.random() < 0.5
    ):
        return round(rng.uniform(1, 100), 1)
    if "string" in usable_types:
        title = field_schema.get("title") or name.replace("_", " ")
        return _string_value(name, title, rng, reference_year)
    raise ValueError(f"No supported non-null type for field {name!r}")


def generate_product(
    category: CategoryCode,
    index: int,
    *,
    rng: random.Random,
    nullable_rate: float,
    reference_year: int,
) -> ProductModel:
    """Generate and validate one product in the requested category."""

    model = CATEGORY_MODEL_BY_CODE[category]
    prefix, brands, price_range = _CATEGORY_PROFILES[category]
    brand = rng.choice(brands)
    original_price = _rounded_price(rng, *price_range)
    discounted = rng.random() < 0.7
    sale_price = (
        round(original_price * rng.choice((0.8, 0.85, 0.9)) / 10_000) * 10_000
        if discounted
        else None
    )
    sequence = index + 1

    common_values: dict[str, object] = {
        "brand": brand,
        "brand_id": brand.lower().replace(" ", "-"),
        "category_code": category.value,
        "category_name": CATEGORY_TITLE_BY_CODE[category],
        "gia_goc": original_price,
        "gia_khuyen_mai": sale_price,
        "khuyen_mai_qua": (
            rng.choice(("Tặng voucher", "Tặng phụ kiện", "Miễn phí lắp đặt"))
            if discounted
            else "Không có"
        ),
        "model_code": f"{prefix}-{reference_year}-{sequence:06d}",
        "productidweb": str(1_000_000 + sequence),
        "sku": f"{prefix}{sequence:08d}",
    }

    payload: dict[str, object] = {}
    for name, field_schema in _model_properties(model).items():
        if name in common_values:
            value = common_values[name]
            if value is None and "null" not in _json_types(field_schema):
                value = original_price
            payload[name] = value
        else:
            payload[name] = _field_value(
                name,
                field_schema,
                rng=rng,
                nullable_rate=nullable_rate,
                reference_year=reference_year,
            )
    return model.model_validate(payload)


def generate_catalog(config: GenerationConfig | None = None) -> ProductCatalog:
    """Generate a complete, validated product catalog."""

    config = config or GenerationConfig()
    rng = random.Random(config.seed)
    schedule = [
        config.categories[index % len(config.categories)]
        for index in range(config.count)
    ]
    rng.shuffle(schedule)
    products = [
        generate_product(
            category,
            index,
            rng=rng,
            nullable_rate=config.nullable_rate,
            reference_year=config.reference_year,
        )
        for index, category in enumerate(schedule)
    ]
    return ProductCatalog(products=products)


def catalog_to_json(catalog: ProductCatalog, *, indent: int = 2) -> str:
    """Serialize a catalog to readable UTF-8 JSON text."""

    return json.dumps(
        catalog.model_dump(mode="json"),
        ensure_ascii=False,
        indent=indent,
    )


def write_catalog(catalog: ProductCatalog, output_path: str | Path) -> Path:
    """Atomically write a validated catalog JSON document."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        catalog_to_json(catalog) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary_path.replace(path)
    return path
