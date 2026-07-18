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
from .models import AuthSession, Base, OtpChallenge, User
from .postgres import PostgresDatabase, get_db_session, get_postgres, postgres

__all__ = [
    "AuthSession",
    "Base",
    "ElasticsearchClient",
    "ElasticsearchRequestError",
    "OtpChallenge",
    "PostgresDatabase",
    "User",
    "elasticsearch",
    "get_db_session",
    "get_elasticsearch",
    "get_postgres",
    "postgres",
]
