"""Generate reproducible product catalog JSON data."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
PositiveWeight = Annotated[
    float,
    Field(gt=0, allow_inf_nan=False),
]
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "data-issue.yaml"
)


class ConfigLoadError(ValueError):
    """Raised when a generation configuration file cannot be parsed."""


class GenerationConfig(BaseModel):
    """Validated inputs for deterministic catalog generation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    count: PositiveCount = 100
    seed: int = 0
    categories: tuple[CategoryCode, ...] = tuple(CategoryCode)
    category_weights: dict[CategoryCode, PositiveWeight] = Field(
        default_factory=dict
    )
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

    @model_validator(mode="after")
    def validate_category_weights(self) -> GenerationConfig:
        unselected = set(self.category_weights) - set(self.categories)
        if unselected:
            names = ", ".join(sorted(category.value for category in unselected))
            raise ValueError(
                f"category weights reference unselected categories: {names}"
            )
        return self

    def weight_for(self, category: CategoryCode) -> float:
        """Return the configured weight or the equal-weight default."""

        return self.category_weights.get(category, 1.0)


def load_generation_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> GenerationConfig:
    """Load and validate generation settings from a YAML file."""

    path = Path(config_path)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Invalid YAML in generation config {path}: {exc}") from exc

    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ConfigLoadError(
            f"Generation config {path} must contain a YAML mapping"
        )

    values = dict(document)
    categories = values.get("categories")
    if isinstance(categories, list):
        try:
            values["categories"] = tuple(
                CategoryCode(category) for category in categories
            )
        except ValueError as exc:
            raise ConfigLoadError(
                f"Invalid category in generation config {path}: {exc}"
            ) from exc

    category_weights = values.get("category_weights")
    if isinstance(category_weights, dict):
        try:
            values["category_weights"] = {
                CategoryCode(category): weight
                for category, weight in category_weights.items()
            }
        except ValueError as exc:
            raise ConfigLoadError(
                f"Invalid category weight in generation config {path}: {exc}"
            ) from exc

    try:
        return GenerationConfig.model_validate(values)
    except ValueError as exc:
        raise ConfigLoadError(
            f"Invalid generation config {path}: {exc}"
        ) from exc


@dataclass(slots=True)
class GenerationContext:
    """Shared deterministic state for one catalog generation run."""

    config: GenerationConfig
    rng: random.Random

    @classmethod
    def from_config(cls, config: GenerationConfig) -> GenerationContext:
        return cls(config=config, rng=random.Random(config.seed))


def allocate_category_counts(
    config: GenerationConfig,
) -> dict[CategoryCode, int]:
    """Allocate the exact product count with largest-remainder rounding."""

    total_weight = sum(config.weight_for(category) for category in config.categories)
    quotas = {
        category: config.count * config.weight_for(category) / total_weight
        for category in config.categories
    }
    counts = {category: int(quotas[category]) for category in config.categories}
    remaining = config.count - sum(counts.values())
    order = {category: index for index, category in enumerate(config.categories)}
    ranked = sorted(
        config.categories,
        key=lambda category: (
            -(quotas[category] - counts[category]),
            order[category],
        ),
    )
    for category in ranked[:remaining]:
        counts[category] += 1
    return counts


def _category_schedule(context: GenerationContext) -> list[CategoryCode]:
    counts = allocate_category_counts(context.config)
    schedule = [
        category
        for category in context.config.categories
        for _ in range(counts[category])
    ]
    context.rng.shuffle(schedule)
    return schedule


@dataclass(frozen=True, slots=True)
class CategoryProfile:
    """Shared commercial characteristics for one product category."""

    identifier_prefix: str
    brands: tuple[str, ...]
    price_range: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Promotion:
    """Internally consistent promotional price and description."""

    price: int | None
    description: str | None


_CATEGORY_PROFILES: dict[CategoryCode, CategoryProfile] = {
    CategoryCode.TU_LANH: CategoryProfile(
        "TL",
        ("Samsung", "LG", "Panasonic"),
        (5_000_000, 45_000_000),
    ),
    CategoryCode.MAY_LANH: CategoryProfile(
        "ML",
        ("Daikin", "Panasonic", "LG"),
        (6_000_000, 35_000_000),
    ),
    CategoryCode.MAY_GIAT: CategoryProfile(
        "MG",
        ("LG", "Samsung", "Electrolux"),
        (5_000_000, 30_000_000),
    ),
    CategoryCode.MAY_SAY_QUAN_AO: CategoryProfile(
        "MS",
        ("Electrolux", "LG", "Bosch"),
        (8_000_000, 35_000_000),
    ),
    CategoryCode.MAY_RUA_CHEN: CategoryProfile(
        "RC",
        ("Bosch", "Electrolux", "Hafele"),
        (9_000_000, 45_000_000),
    ),
    CategoryCode.TU_MAT_TU_DONG: CategoryProfile(
        "TD",
        ("Sanaky", "Alaska", "Aqua"),
        (5_000_000, 35_000_000),
    ),
    CategoryCode.MAY_NUOC_NONG: CategoryProfile(
        "NN",
        ("Ariston", "Ferroli", "Panasonic"),
        (2_000_000, 15_000_000),
    ),
    CategoryCode.MICRO_KARAOKE: CategoryProfile(
        "MK",
        ("JBL", "Paramax", "Shure"),
        (1_000_000, 12_000_000),
    ),
    CategoryCode.MICRO_THU_AM_DIEN_THOAI: CategoryProfile(
        "MT",
        ("Rode", "DJI", "Boya"),
        (800_000, 12_000_000),
    ),
    CategoryCode.DONG_HO_THONG_MINH: CategoryProfile(
        "DH",
        ("Apple", "Samsung", "Garmin"),
        (2_000_000, 25_000_000),
    ),
    CategoryCode.MAY_TINH_DE_BAN: CategoryProfile(
        "PC",
        ("Asus", "Dell", "HP"),
        (8_000_000, 60_000_000),
    ),
    CategoryCode.MAN_HINH_MAY_TINH: CategoryProfile(
        "MH",
        ("LG", "Dell", "Asus"),
        (2_000_000, 25_000_000),
    ),
    CategoryCode.MAY_IN: CategoryProfile(
        "MI",
        ("Canon", "Brother", "HP"),
        (2_000_000, 20_000_000),
    ),
    CategoryCode.MAY_TINH_BANG: CategoryProfile(
        "TB",
        ("Apple", "Samsung", "Xiaomi"),
        (4_000_000, 35_000_000),
    ),
}

_COUNTRIES = ("Việt Nam", "Thái Lan", "Trung Quốc", "Malaysia", "Hàn Quốc")
_MATERIALS = (
    "Thép không gỉ",
    "Nhựa ABS",
    "Hợp kim nhôm",
    "Kính cường lực",
)
_TECHNOLOGIES = (
    "Inverter tiết kiệm điện",
    "Điều khiển thông minh",
    "Cảm biến tự động",
    "Khử khuẩn tiên tiến",
)
_UTILITIES = (
    "Hẹn giờ và tự khởi động lại",
    "Điều khiển từ xa qua ứng dụng",
    "Cảnh báo trạng thái hoạt động",
    "Chế độ vận hành tiết kiệm năng lượng",
)
_CONNECTIONS = ("Bluetooth 5.3", "Wi-Fi", "USB-C", "HDMI")
_PROMOTIONAL_GIFTS = (
    "Tặng voucher 300.000đ",
    "Tặng phụ kiện chính hãng",
    "Miễn phí lắp đặt",
)
_NO_PROMOTION_DESCRIPTION = "Không có khuyến mãi"
_RELEASE_YEAR_FIELDS = frozenset({"nam_san_xuat", "thoi_gian_ra_mat"})
_UTILITY_FIELDS = frozenset(
    {
        "tien_ich",
        "tien_ich_khac",
        "tinh_nang_an_toan",
        "tinh_nang_co_ban",
        "tinh_nang_dac_biet",
        "tinh_nang_khac",
    }
)
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


def _is_nullable(field_schema: dict[str, Any]) -> bool:
    return "null" in _json_types(field_schema)


def _rounded_price(rng: random.Random, low: int, high: int) -> int:
    price_step = 100_000
    return rng.randrange(low // price_step, high // price_step + 1) * price_step


def _brand_id(brand: str) -> str:
    return f"brand-{brand.casefold().replace(' ', '-')}"


def _identity_values(
    *,
    category: CategoryCode,
    index: int,
    profile: CategoryProfile,
    brand: str,
    reference_year: int,
) -> dict[str, str]:
    sequence = index + 1
    prefix = profile.identifier_prefix
    return {
        "brand": brand,
        "brand_id": _brand_id(brand),
        "category_code": category.value,
        "category_name": CATEGORY_TITLE_BY_CODE[category],
        "model_code": f"{prefix}-{reference_year}-{sequence:06d}",
        "productidweb": str(1_000_000 + sequence),
        "sku": f"{prefix}{sequence:08d}",
    }


def _promotion(
    *,
    original_price: int,
    description_nullable: bool,
    rng: random.Random,
) -> Promotion:
    if rng.random() >= 0.7:
        description = None if description_nullable else _NO_PROMOTION_DESCRIPTION
        return Promotion(price=None, description=description)

    discount_percent = rng.choice((10, 20))
    promotional_price = original_price * (100 - discount_percent) // 100
    gift = rng.choice(_PROMOTIONAL_GIFTS)
    return Promotion(
        price=promotional_price,
        description=f"Giảm {discount_percent}% - {gift}",
    )


def _release_year_value(
    allowed_types: tuple[str, ...],
    rng: random.Random,
    reference_year: int,
) -> int | str:
    year = rng.randint(max(2015, reference_year - 8), reference_year)
    if "integer" in allowed_types:
        return year
    return str(year)


def _is_dimension_field(name: str) -> bool:
    return name == "kich_thuoc" or name.startswith(
        ("cao", "dai", "ngang", "rong", "sau", "day", "do_day", "kich_thuoc")
    )


def _dimension_value(
    name: str,
    allowed_types: tuple[str, ...],
    rng: random.Random,
) -> int | float | str:
    if name == "kich_thuoc":
        dimensions = (
            rng.randint(50, 250),
            rng.randint(30, 150),
            rng.randint(10, 100),
        )
        return " x ".join(str(value) for value in dimensions) + " mm"

    if "man_hinh" in name or name == "kich_thuoc_mat":
        size_inches = round(rng.uniform(1.3, 34.0), 1)
        if "number" in allowed_types and (
            "string" not in allowed_types or rng.random() < 0.5
        ):
            return size_inches
        return f"{size_inches} inch"

    thin_dimension = (
        name == "day"
        or name.startswith("do_day")
        or name.endswith("_day")
    )
    millimeters = (
        rng.randint(5, 200) if thin_dimension else rng.randint(20, 2_000)
    )
    if "integer" in allowed_types and (
        "string" not in allowed_types or rng.random() < 0.5
    ):
        return millimeters
    if "number" in allowed_types and (
        "string" not in allowed_types or rng.random() < 0.5
    ):
        return float(millimeters)
    return f"{millimeters} mm"


def _weight_value(
    allowed_types: tuple[str, ...],
    rng: random.Random,
) -> int | float | str:
    kilograms = rng.randint(1, 150)
    if "integer" in allowed_types and (
        "string" not in allowed_types or rng.random() < 0.5
    ):
        return kilograms
    if "number" in allowed_types and (
        "string" not in allowed_types or rng.random() < 0.5
    ):
        return float(kilograms)
    return f"{kilograms} kg"


def _material_value(rng: random.Random) -> str:
    return rng.choice(_MATERIALS)


def _technology_value(rng: random.Random) -> str:
    return rng.choice(_TECHNOLOGIES)


def _utility_value(rng: random.Random) -> str:
    return rng.choice(_UTILITIES)


def _integer_value(name: str, rng: random.Random) -> int:
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
) -> str:
    if name == "san_xuat_tai":
        return rng.choice(_COUNTRIES)
    if name in {"ket_noi", "cong_ket_noi", "cong_giao_tiep", "wifi", "bluetooth"}:
        return rng.choice(_CONNECTIONS)
    if "dung_luong_pin" in name:
        return f"{rng.randrange(1_000, 10_001, 100)} mAh"
    if "dung_tich" in name:
        return f"{rng.randint(10, 700)} lít"
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
    if name in _RELEASE_YEAR_FIELDS:
        return _release_year_value(usable_types, rng, reference_year)
    if _is_dimension_field(name):
        return _dimension_value(name, usable_types, rng)
    if "khoi_luong" in name:
        return _weight_value(usable_types, rng)
    if "chat_lieu" in name:
        return _material_value(rng)
    if "cong_nghe" in name:
        return _technology_value(rng)
    if name in _UTILITY_FIELDS or name.startswith("tinh_nang_"):
        return _utility_value(rng)
    if "integer" in usable_types and (
        "string" not in usable_types or rng.random() < 0.5
    ):
        return _integer_value(name, rng)
    if "number" in usable_types and (
        "string" not in usable_types or rng.random() < 0.5
    ):
        return round(rng.uniform(1, 100), 1)
    if "string" in usable_types:
        title = field_schema.get("title") or name.replace("_", " ")
        return _string_value(name, title, rng)
    raise ValueError(f"No supported non-null type for field {name!r}")


def generate_product(
    category: CategoryCode,
    index: int,
    context: GenerationContext,
) -> ProductModel:
    """Generate and validate one product in the requested category."""

    rng = context.rng
    nullable_rate = context.config.nullable_rate
    reference_year = context.config.reference_year
    model = CATEGORY_MODEL_BY_CODE[category]
    properties = _model_properties(model)
    profile = _CATEGORY_PROFILES[category]
    brand = rng.choice(profile.brands)
    original_price = _rounded_price(rng, *profile.price_range)
    promotion = _promotion(
        original_price=original_price,
        description_nullable=_is_nullable(properties["khuyen_mai_qua"]),
        rng=rng,
    )

    shared_values: dict[str, object] = {
        **_identity_values(
            category=category,
            index=index,
            profile=profile,
            brand=brand,
            reference_year=reference_year,
        ),
        "gia_goc": original_price,
        "gia_khuyen_mai": promotion.price,
        "khuyen_mai_qua": promotion.description,
    }

    payload: dict[str, object] = {}
    for name, field_schema in properties.items():
        if name in shared_values:
            payload[name] = shared_values[name]
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

    config = config or load_generation_config()
    context = GenerationContext.from_config(config)
    schedule = _category_schedule(context)
    products = [
        generate_product(category, index, context)
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
