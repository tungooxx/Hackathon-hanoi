"""Shared database clients.

Usage:
    from db import elasticsearch

    result = await elasticsearch.search({"query": {"match_all": {}}})
"""

from .elasticsearch import (
    ElasticsearchClient,
    ElasticsearchRequestError,
    elasticsearch,
    get_elasticsearch,
)
from .qdrant import (
    QdrantClient,
    QdrantRequestError,
    get_qdrant,
    qdrant,
)

__all__ = [
    "ElasticsearchClient",
    "ElasticsearchRequestError",
    "elasticsearch",
    "get_elasticsearch",
    "QdrantClient",
    "QdrantRequestError",
    "qdrant",
    "get_qdrant",
]
