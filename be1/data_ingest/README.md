# Product ingestion

`ingest_products.py` reads `products_detail.xlsx` directly and creates one
Elasticsearch document per row in the `products` sheet. Rows from `specs` are
stored in that document as nested `{key, value}` objects.

The importer uses only the Python standard library. It:

- creates an explicit index mapping;
- preserves product codes as strings, including leading zeroes;
- indexes Vietnamese text with lowercase and ASCII folding;
- sends products through the Elasticsearch bulk API in batches;
- restores the normal refresh interval and verifies the document count.

## Run

From this directory:

```bash
./ingest.sh
```

The wrapper starts Elasticsearch and recreates the `products` index. To update
documents without deleting the existing index:

```bash
./ingest.sh --no-recreate-index
```

Validate the entire workbook without writing to Elasticsearch:

```bash
python3 ingest_products.py --dry-run
```

Configuration can be supplied through command-line flags or these environment
variables:

```text
ELASTICSEARCH_URL=http://127.0.0.1:9200
ELASTICSEARCH_PRODUCTS_INDEX=products
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=
```

Example full-text search:

```bash
curl -s http://127.0.0.1:9200/products/_search \
  -H 'Content-Type: application/json' \
  -d '{"query":{"match":{"search_text":"may lanh inverter"}}}'
```

Example matching a specification key and value on the same nested object:

```bash
curl -s http://127.0.0.1:9200/products/_search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "nested": {
        "path": "specs",
        "query": {
          "bool": {
            "must": [
              {"match": {"specs.key": "Dung lượng pin"}},
              {"match": {"specs.value": "3000 mAh"}}
            ]
          }
        }
      }
    }
  }'
```
