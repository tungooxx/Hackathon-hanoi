"""Sinh fixtures/may_lanh.json từ file excel gốc của DMX.

Chỉ dùng stdlib (không cần openpyxl). Lấy các dòng có giá — dòng thiếu spec
vẫn giữ, field thiếu để null (bot phải thừa nhận thiếu thay vì bịa).

Usage: python scripts/make_fixture.py [đường-dẫn-xlsx]
"""
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX = sys.argv[1] if len(sys.argv) > 1 else "/Users/trHien/Downloads/data-mẫu-của-dmx.xlsx"
OUT = Path(__file__).resolve().parent.parent / "fixtures" / "may_lanh.json"
SHEET = "xl/worksheets/sheet2.xml"  # Máy lạnh


def col_idx(ref: str) -> int:
    col = 0
    for ch in ref:
        if ch.isalpha():
            col = col * 26 + ord(ch.upper()) - 64
        else:
            break
    return col - 1


def parse_area(s: str) -> tuple[float | None, float | None]:
    # "Dưới 15m² (...)" / "Từ 15 - 20m² (...)" / "Từ 40 - 60m² (...)"
    if not s:
        return None, None
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*m²", s.replace(",", "."))]
    if s.startswith("Dưới") and nums:
        return 0.0, nums[0]
    both = re.findall(r"(\d+(?:\.\d+)?)", s)
    if len(both) >= 2:
        return float(both[0]), float(both[1])
    return None, None


def parse_noise(s: str) -> float | None:
    # "Dàn lạnh: 21 - 39 dB - Dàn nóng: 50 dB" -> lấy min dàn lạnh
    if not s:
        return None
    m = re.search(r"Dàn lạnh:\s*([\d./ -]+)dB", s)
    part = m.group(1) if m else s
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", part)]
    return min(nums) if nums else None


def parse_stars(s: str) -> int | None:
    m = re.search(r"(\d)\s*sao", s or "")
    return int(m.group(1)) if m else None


def parse_price(s: str) -> int | None:
    s = (s or "").strip().replace(",", "").replace(".", "")
    return int(s) if s.isdigit() and int(s) > 0 else None


def main() -> None:
    z = zipfile.ZipFile(XLSX)
    strings = [
        "".join(t.text or "" for t in si.iter(M + "t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml"))
    ]
    rows = list(ET.fromstring(z.read(SHEET)).iter(M + "row"))

    def row_vals(r) -> dict[int, str]:
        d = {}
        for c in r.iter(M + "c"):
            v = c.find(M + "v")
            val = v.text if v is not None else ""
            if c.get("t") == "s" and val:
                val = strings[int(val)]
            d[col_idx(c.get("r"))] = val
        return d

    hdr = row_vals(rows[0])
    idx = {v: k for k, v in hdr.items()}
    products = []
    for r in rows[1:]:
        d = row_vals(r)

        def g(col: str) -> str:
            return (d.get(idx[col], "") or "").strip()

        price_orig = parse_price(g("giá gốc"))
        price_sale = parse_price(g("giá khuyến mãi"))
        if price_orig is None and price_sale is None:
            continue  # dòng không có giá thì không bán được -> bỏ
        area_min, area_max = parse_area(g("Phạm vi sử dụng"))
        inverter_raw = g("Loại Inverter") or g("Công nghệ tiết kiệm điện")
        brand = g("brand")
        loai = g("Loại máy")
        name_bits = [f"Máy lạnh {brand}"]
        if "Inverter" in inverter_raw:
            name_bits.append("Inverter")
        if area_max:
            name_bits.append(f"(phòng {'dưới ' + str(int(area_max)) if not area_min else str(int(area_min)) + '-' + str(int(area_max))}m²)")
        products.append({
            "sku": g("sku"),
            "model_code": g("model_code"),
            "name": " ".join(name_bits),
            "brand": brand,
            "category": "may_lanh",
            "price_original": price_orig,
            "price_sale": price_sale or price_orig,
            "promo_gift": g("khuyến mãi quà") or None,
            "area_min_m2": area_min,
            "area_max_m2": area_max,
            "noise_db_min": parse_noise(g("Độ ồn")),
            "inverter": "Inverter" in inverter_raw if inverter_raw else None,
            "energy_stars": parse_stars(g("Nhãn năng lượng")),
            "loai_may": loai or None,
            "warranty_parts": g("Bảo hành bộ phận") or None,
            "utilities": g("Tiện ích") or None,
            "made_in": g("Sản xuất tại") or None,
        })
    OUT.write_text(json.dumps(products, ensure_ascii=False, indent=1))
    with_area = sum(1 for p in products if p["area_max_m2"])
    print(f"{len(products)} sản phẩm có giá (trong đó {with_area} có diện tích) -> {OUT}")


if __name__ == "__main__":
    main()
