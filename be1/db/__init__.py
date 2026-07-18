"""Shared database clients and persistence models.

Usage:
    from db import elasticsearch, postgres

    result = await elasticsearch.search({"query": {"match_all": {}}})
"""

from .elasticsearch import (
    ElasticsearchClient,
    ElasticsearchRequestError,
    elasticsearch,
    get_elasticsearch,
)
from .models import AuthLoginAttempt, AuthSession, Base, User
from .postgres import PostgresDatabase, get_db_session, get_postgres, postgres

__all__ = [
    "AuthLoginAttempt",
    "AuthSession",
    "Base",
    "ElasticsearchClient",
    "ElasticsearchRequestError",
    "PostgresDatabase",
    "User",
    "elasticsearch",
    "get_db_session",
    "get_elasticsearch",
    "get_postgres",
    "postgres",
]
