#!/usr/bin/env python3
"""Ingest products_detail.xlsx into Elasticsearch without third-party packages."""

from __future__ import annotations

import argparse
import base64
import json
import os
import posixpath
import re
import sys
import time
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
M = f"{{{MAIN_NS}}}"
SCRIPT_DIR = Path(__file__).resolve().parent

PRODUCT_HEADERS = {
    "product_id",
    "tên sản phẩm",
    "category_name",
    "category_id",
    "brand",
    "Giá gốc",
    "Giá khuyến mãi",
    "rating_vote",
    "quantity_sold",
    "màu sắc",
    "productcode",
    "producttype",
    "onlineSaleOnly",
    "Phụ kiện đi kèm",
    "chính sách bảo hành",
    "promotion",
    "outstanding",
    "url",
    "url_image",
    "time_crawler",
}
SPEC_HEADERS = {"product_id", "tên sản phẩm", "spec_key", "spec_value"}
INDEX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class IngestError(RuntimeError):
    pass


def column_index(cell_reference: str) -> int:
    result = 0
    for character in cell_reference:
        if not character.isalpha():
            break
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


class XlsxReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = zipfile.ZipFile(path)
        self.shared_strings = self._load_shared_strings()
        self.sheets = self._load_sheet_paths()

    def __enter__(self) -> XlsxReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.archive.close()

    def _load_shared_strings(self) -> list[str]:
        path = "xl/sharedStrings.xml"
        if path not in self.archive.namelist():
            return []
        root = ET.fromstring(self.archive.read(path))
        return [
            "".join(node.text or "" for node in item.iter(M + "t"))
            for item in root.iter(M + "si")
        ]

    def _load_sheet_paths(self) -> dict[str, str]:
        workbook = ET.fromstring(self.archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(
            self.archive.read("xl/_rels/workbook.xml.rels")
        )
        targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships.iter(f"{{{PACKAGE_REL_NS}}}Relationship")
        }
        result: dict[str, str] = {}
        for sheet in workbook.iter(M + "sheet"):
            relationship_id = sheet.attrib[f"{{{DOCUMENT_REL_NS}}}id"]
            target = targets[relationship_id]
            if target.startswith("/"):
                path = target.lstrip("/")
            else:
                path = posixpath.normpath(posixpath.join("xl", target))
            result[sheet.attrib["name"]] = path
        return result

    def _cell_value(self, cell: ET.Element) -> str | None:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            text_nodes = list(cell.iter(M + "t"))
            return "".join(node.text or "" for node in text_nodes) or None

        value_node = cell.find(M + "v")
        if value_node is None or value_node.text is None:
            return None
        value = value_node.text
        if cell_type == "s":
            return self.shared_strings[int(value)]
        if cell_type == "b":
            return "true" if value == "1" else "false"
        return value

    def records(self, sheet_name: str) -> Iterator[tuple[int, dict[str, str | None]]]:
        if sheet_name not in self.sheets:
            available = ", ".join(sorted(self.sheets))
            raise IngestError(
                f"Sheet {sheet_name!r} was not found. Available sheets: {available}"
            )

        header: list[str | None] | None = None
        with self.archive.open(self.sheets[sheet_name]) as stream:
            for _event, row in ET.iterparse(stream, events=("end",)):
                if row.tag != M + "row":
                    continue

                row_number = int(row.attrib.get("r", "0"))
                values: dict[int, str | None] = {}
                for cell in row.findall(M + "c"):
                    reference = cell.attrib.get("r", "")
                    values[column_index(reference)] = self._cell_value(cell)

                if header is None:
                    last_column = max(values, default=-1)
                    header = [values.get(index) for index in range(last_column + 1)]
                    if any(name is None for name in header):
                        raise IngestError(
                            f"Sheet {sheet_name!r} has an empty header cell"
                        )
                else:
                    record = {
                        str(name): values.get(index)
                        for index, name in enumerate(header)
                    }
                    yield row_number, record
                row.clear()


def validate_headers(
    record: dict[str, str | None],
    required: set[str],
    sheet_name: str,
) -> None:
    missing = sorted(required - record.keys())
    if missing:
        raise IngestError(
            f"Sheet {sheet_name!r} is missing columns: {', '.join(missing)}"
        )


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def required_text(value: str | None, field: str, row_number: int) -> str:
    cleaned = optional_text(value)
    if cleaned is None:
        raise IngestError(f"Row {row_number}: {field!r} must not be empty")
    return cleaned


def optional_float(value: str | None, field: str, row_number: int) -> float | None:
    cleaned = optional_text(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise IngestError(
            f"Row {row_number}: {field!r} is not a number: {cleaned!r}"
        ) from exc


def required_int(value: str | None, field: str, row_number: int) -> int:
    cleaned = required_text(value, field, row_number)
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise IngestError(
            f"Row {row_number}: {field!r} is not an integer: {cleaned!r}"
        ) from exc
    if number != number.to_integral_value():
        raise IngestError(
            f"Row {row_number}: {field!r} is not an integer: {cleaned!r}"
        )
    return int(number)


def required_bool(value: str | None, field: str, row_number: int) -> bool:
    cleaned = required_text(value, field, row_number).lower()
    if cleaned in {"true", "1"}:
        return True
    if cleaned in {"false", "0"}:
        return False
    raise IngestError(f"Row {row_number}: {field!r} is not boolean: {cleaned!r}")


def index_definition() -> dict[str, Any]:
    text_with_raw = {
        "type": "text",
        "analyzer": "folded_text",
        "fields": {
            "raw": {
                "type": "keyword",
                "normalizer": "folded_keyword",
                "ignore_above": 512,
            }
        },
    }
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "-1",
            "analysis": {
                "analyzer": {
                    "folded_text": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    }
                },
                "normalizer": {
                    "folded_keyword": {
                        "type": "custom",
                        "filter": ["lowercase", "asciifolding"],
                    }
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "product_id": {"type": "long"},
                "product_name": text_with_raw,
                "category_name": text_with_raw,
                "category_id": {"type": "long"},
                "brand": text_with_raw,
                "original_price": {"type": "long"},
                "sale_price": {"type": "long"},
                "rating_vote": {"type": "float"},
                "quantity_sold": {"type": "keyword"},
                "color": text_with_raw,
                "product_code": {"type": "keyword"},
                "product_type": {"type": "integer"},
                "online_sale_only": {"type": "boolean"},
                "included_accessories": {
                    "type": "text",
                    "analyzer": "folded_text",
                },
                "warranty_policy": {"type": "text", "analyzer": "folded_text"},
                "promotion": {"type": "text", "analyzer": "folded_text"},
                "outstanding": {"type": "text", "analyzer": "folded_text"},
                "url": {"type": "keyword", "index": False, "doc_values": False},
                "image_url": {
                    "type": "keyword",
                    "index": False,
                    "doc_values": False,
                },
                "crawled_at": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss||strict_date_optional_time",
                },
                "specs_count": {"type": "integer"},
                "specs": {
                    "type": "nested",
                    "properties": {
                        "key": {
                            "type": "text",
                            "analyzer": "folded_text",
                            "fields": {
                                "raw": {
                                    "type": "keyword",
                                    "normalizer": "folded_keyword",
                                    "ignore_above": 512,
                                }
                            },
                        },
                        "value": {
                            "type": "text",
                            "analyzer": "folded_text",
                            "fields": {
                                "raw": {
                                    "type": "keyword",
                                    "normalizer": "folded_keyword",
                                    "ignore_above": 2048,
                                }
                            },
                        },
                    },
                },
                "search_text": {"type": "text", "analyzer": "folded_text"},
            },
        },
    }


def build_document(
    row: dict[str, str | None],
    row_number: int,
    specs: list[dict[str, str]],
) -> dict[str, Any]:
    document = {
        "product_id": required_int(row["product_id"], "product_id", row_number),
        "product_name": optional_text(row["tên sản phẩm"]),
        "category_name": required_text(
            row["category_name"], "category_name", row_number
        ),
        "category_id": required_int(row["category_id"], "category_id", row_number),
        "brand": optional_text(row["brand"]),
        "original_price": required_int(row["Giá gốc"], "Giá gốc", row_number),
        "sale_price": required_int(
            row["Giá khuyến mãi"], "Giá khuyến mãi", row_number
        ),
        "rating_vote": optional_float(row["rating_vote"], "rating_vote", row_number),
        "quantity_sold": optional_text(row["quantity_sold"]),
        "color": optional_text(row["màu sắc"]),
        "product_code": optional_text(row["productcode"]),
        "product_type": required_int(row["producttype"], "producttype", row_number),
        "online_sale_only": required_bool(
            row["onlineSaleOnly"], "onlineSaleOnly", row_number
        ),
        "included_accessories": optional_text(row["Phụ kiện đi kèm"]),
        "warranty_policy": optional_text(row["chính sách bảo hành"]),
        "promotion": optional_text(row["promotion"]),
        "outstanding": optional_text(row["outstanding"]),
        "url": required_text(row["url"], "url", row_number),
        "image_url": optional_text(row["url_image"]),
        "crawled_at": required_text(row["time_crawler"], "time_crawler", row_number),
        "specs_count": len(specs),
        "specs": specs,
    }
    searchable_values = [
        document["product_name"],
        document["category_name"],
        document["brand"],
        document["color"],
        document["included_accessories"],
        document["warranty_policy"],
        document["promotion"],
        document["outstanding"],
    ]
    searchable_values.extend(
        value
        for spec in specs
        for value in (spec["key"], spec["value"])
    )
    document["search_text"] = "\n".join(
        str(value) for value in searchable_values if value is not None
    )
    return document


class ElasticsearchClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        username: str | None,
        password: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Accept": "application/json"}
        if bool(username) != bool(password):
            raise IngestError(
                "Set both ELASTICSEARCH_USERNAME and ELASTICSEARCH_PASSWORD"
            )
        if username and password:
            credentials = base64.b64encode(
                f"{username}:{password}".encode()
            ).decode()
            self.headers["Authorization"] = f"Basic {credentials}"

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | bytes | None = None,
        *,
        content_type: str = "application/json",
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, Any] | None]:
        if isinstance(payload, dict):
            data = json.dumps(payload, ensure_ascii=False).encode()
        else:
            data = payload
        headers = dict(self.headers)
        if data is not None:
            headers["Content-Type"] = content_type

        for attempt in range(1, 4):
            request = Request(
                f"{self.base_url}{path}",
                data=data,
                headers=headers,
                method=method,
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    status = response.status
                    body = response.read()
            except HTTPError as exc:
                status = exc.code
                body = exc.read()
                if status not in expected and status in {429, 502, 503, 504}:
                    if attempt < 3:
                        time.sleep(2 ** (attempt - 1))
                        continue
            except URLError as exc:
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise IngestError(
                    f"Cannot connect to Elasticsearch at {self.base_url}: {exc.reason}"
                ) from exc

            parsed = json.loads(body) if body else None
            if status not in expected:
                details = json.dumps(parsed, ensure_ascii=False)[:2000]
                raise IngestError(
                    f"Elasticsearch {method} {path} returned HTTP {status}: {details}"
                )
            return status, parsed
        raise AssertionError("unreachable")

    def prepare_index(self, index_name: str, recreate: bool) -> None:
        encoded_index = quote(index_name, safe="")
        status, _ = self.request(
            "HEAD", f"/{encoded_index}", expected=(200, 404)
        )
        if status == 200 and recreate:
            self.request("DELETE", f"/{encoded_index}")
            status = 404
        if status == 404:
            self.request("PUT", f"/{encoded_index}", index_definition())
            print(f"Created index {index_name!r}")
        else:
            self.request(
                "PUT",
                f"/{encoded_index}/_settings",
                {"index": {"refresh_interval": "-1"}},
            )
            print(f"Using existing index {index_name!r}")

    def bulk_index(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> None:
        lines: list[str] = []
        for document in documents:
            lines.append(
                json.dumps(
                    {"index": {"_id": str(document["product_id"])}},
                    separators=(",", ":"),
                )
            )
            lines.append(
                json.dumps(document, ensure_ascii=False, separators=(",", ":"))
            )
        payload = ("\n".join(lines) + "\n").encode()
        encoded_index = quote(index_name, safe="")
        _, response = self.request(
            "POST",
            (
                f"/{encoded_index}/_bulk"
                "?filter_path=errors,items.*.status,items.*.error"
            ),
            payload,
            content_type="application/x-ndjson",
        )
        if response and response.get("errors"):
            failures = []
            for item in response.get("items", []):
                result = item.get("index", {})
                if result.get("status", 500) >= 300:
                    failures.append(result)
                if len(failures) == 10:
                    break
            raise IngestError(
                "Bulk indexing failed: "
                + json.dumps(failures, ensure_ascii=False)[:4000]
            )

    def restore_refresh_interval(self, index_name: str) -> None:
        encoded_index = quote(index_name, safe="")
        self.request(
            "PUT",
            f"/{encoded_index}/_settings",
            {"index": {"refresh_interval": "1s"}},
        )

    def finish_index(self, index_name: str) -> int:
        encoded_index = quote(index_name, safe="")
        self.restore_refresh_interval(index_name)
        self.request("POST", f"/{encoded_index}/_refresh")
        _, response = self.request("GET", f"/{encoded_index}/_count")
        return int(response["count"]) if response else 0


def load_specs(
    workbook: XlsxReader,
    progress_every: int,
) -> tuple[dict[int, list[dict[str, str]]], int]:
    specs_by_product: dict[int, list[dict[str, str]]] = defaultdict(list)
    total = 0
    for row_number, row in workbook.records("specs"):
        if total == 0:
            validate_headers(row, SPEC_HEADERS, "specs")
        product_id = required_int(row["product_id"], "product_id", row_number)
        specs_by_product[product_id].append(
            {
                "key": required_text(row["spec_key"], "spec_key", row_number),
                "value": required_text(row["spec_value"], "spec_value", row_number),
            }
        )
        total += 1
        if total % progress_every == 0:
            print(f"Read {total:,} specification rows...")
    return specs_by_product, total


def ingest(args: argparse.Namespace) -> None:
    if not args.input.is_file():
        raise IngestError(f"Workbook does not exist: {args.input}")
    if not INDEX_NAME_PATTERN.fullmatch(args.index) or args.index in {".", ".."}:
        raise IngestError(f"Invalid Elasticsearch index name: {args.index!r}")

    client = None
    if not args.dry_run:
        client = ElasticsearchClient(
            args.elasticsearch_url,
            args.timeout,
            args.username,
            args.password,
        )
        client.request("GET", "/")

    index_prepared = False
    try:
        with XlsxReader(args.input) as workbook:
            print(f"Reading specifications from {args.input.name}...")
            specs_by_product, spec_count = load_specs(workbook, args.progress_every)
            print(
                f"Loaded {spec_count:,} specifications for "
                f"{len(specs_by_product):,} products"
            )

            if client:
                client.prepare_index(args.index, args.recreate_index)
                index_prepared = True

            batch: list[dict[str, Any]] = []
            seen_product_ids: set[int] = set()
            product_count = 0
            for row_number, row in workbook.records("products"):
                if product_count == 0:
                    validate_headers(row, PRODUCT_HEADERS, "products")
                product_id = required_int(
                    row["product_id"], "product_id", row_number
                )
                if product_id in seen_product_ids:
                    raise IngestError(
                        f"Duplicate product_id {product_id} at row {row_number}"
                    )
                seen_product_ids.add(product_id)
                batch.append(
                    build_document(
                        row,
                        row_number,
                        specs_by_product.get(product_id, []),
                    )
                )
                product_count += 1

                if len(batch) >= args.batch_size:
                    if client:
                        client.bulk_index(args.index, batch)
                    batch.clear()
                if product_count % args.progress_every == 0:
                    verb = "Indexed" if client else "Validated"
                    print(f"{verb} {product_count:,} products...")

            if batch and client:
                client.bulk_index(args.index, batch)
    except BaseException:
        if client and index_prepared:
            try:
                client.restore_refresh_interval(args.index)
            except IngestError as cleanup_error:
                print(
                    f"Warning: could not restore refresh interval: {cleanup_error}",
                    file=sys.stderr,
                )
        raise

    orphan_ids = specs_by_product.keys() - seen_product_ids
    orphan_spec_count = sum(len(specs_by_product[item]) for item in orphan_ids)
    if orphan_ids:
        print(
            f"Warning: {orphan_spec_count:,} specs reference "
            f"{len(orphan_ids):,} missing products",
            file=sys.stderr,
        )

    if client:
        indexed_count = client.finish_index(args.index)
        if args.recreate_index and indexed_count != product_count:
            raise IngestError(
                f"Expected {product_count:,} indexed products, found {indexed_count:,}"
            )
        print(
            f"Done: indexed {product_count:,} products with "
            f"{spec_count - orphan_spec_count:,} specs into {args.index!r}; "
            f"index now contains {indexed_count:,} documents"
        )
    else:
        print(
            f"Dry run complete: validated {product_count:,} products and "
            f"{spec_count:,} specs; Elasticsearch was not changed"
        )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk ingest products and nested specifications into Elasticsearch."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=SCRIPT_DIR / "products_detail.xlsx",
        help="Path to the XLSX workbook",
    )
    parser.add_argument(
        "--elasticsearch-url",
        default=os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200"),
    )
    parser.add_argument(
        "--index",
        default=os.getenv("ELASTICSEARCH_PRODUCTS_INDEX", "products"),
    )
    parser.add_argument("--batch-size", type=positive_int, default=500)
    parser.add_argument("--progress-every", type=positive_int, default=10_000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--username",
        default=os.getenv("ELASTICSEARCH_USERNAME"),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ELASTICSEARCH_PASSWORD"),
    )
    parser.add_argument(
        "--recreate-index",
        dest="recreate_index",
        action="store_true",
        default=False,
        help="Delete and recreate the target index before ingestion",
    )
    parser.add_argument(
        "--no-recreate-index",
        dest="recreate_index",
        action="store_false",
        help="Do not recreate the target index before ingestion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and transform the workbook without changing Elasticsearch",
    )
    return parser.parse_args()


def main() -> None:
    try:
        ingest(parse_args())
    except (IngestError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
