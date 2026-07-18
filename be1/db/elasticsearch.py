"""Reusable asynchronous Elasticsearch client for application services."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from app.config import (
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_PASSWORD,
    ELASTICSEARCH_TIMEOUT_SECONDS,
    ELASTICSEARCH_URL,
    ELASTICSEARCH_USERNAME,
)


class ElasticsearchRequestError(RuntimeError):
    """An Elasticsearch request failed or returned a non-success response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ElasticsearchClient:
    """Small HTTP client with one shared async connection pool."""

    def __init__(
        self,
        base_url: str,
        default_index: str,
        *,
        username: str = "",
        password: str = "",
        timeout: float = 10.0,
    ) -> None:
        if bool(username) != bool(password):
            raise ValueError(
                "Elasticsearch username and password must be configured together"
            )
        self.base_url = base_url.rstrip("/")
        self.default_index = default_index
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._start_lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._client is not None and not self._client.is_closed

    async def start(self) -> ElasticsearchClient:
        """Create the connection pool if it has not been created yet."""
        if self.is_started:
            return self
        async with self._start_lock:
            if self.is_started:
                return self
            auth = None
            if self.username:
                auth = httpx.BasicAuth(self.username, self.password)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=auth,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "dmx-advisor-be1/1.0",
                },
            )
        return self

    async def close(self) -> None:
        """Close the connection pool."""
        async with self._start_lock:
            client = self._client
            self._client = None
            if client is not None and not client.is_closed:
                await client.aclose()

    async def __aenter__(self) -> ElasticsearchClient:
        return await self.start()

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        """Perform a JSON request against an Elasticsearch API path."""
        if not path.startswith("/"):
            raise ValueError("Elasticsearch request paths must start with '/'")
        client = (await self.start())._client
        assert client is not None

        try:
            response = await client.request(
                method,
                path,
                params=params,
                json=dict(json_body) if json_body is not None else None,
            )
        except httpx.HTTPError as exc:
            raise ElasticsearchRequestError(
                f"Elasticsearch request failed: {method.upper()} {path}: {exc}"
            ) from exc

        if response.is_error:
            try:
                details: Any = response.json()
            except ValueError:
                details = response.text[:2000]
            reason = self._error_reason(details)
            raise ElasticsearchRequestError(
                (
                    f"Elasticsearch returned HTTP {response.status_code} for "
                    f"{method.upper()} {path}: {reason}"
                ),
                status_code=response.status_code,
                details=details,
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ElasticsearchRequestError(
                f"Elasticsearch returned invalid JSON for {method.upper()} {path}",
                status_code=response.status_code,
                details=response.text[:2000],
            ) from exc

    async def ping(self) -> bool:
        """Return whether Elasticsearch is reachable."""
        try:
            await self.request("GET", "/")
        except ElasticsearchRequestError:
            return False
        return True

    async def cluster_health(self, *, index: str | None = None) -> dict[str, Any]:
        """Return cluster health, optionally scoped to an index."""
        path = "/_cluster/health"
        if index is not None:
            path += f"/{self._encoded_index(index)}"
        result = await self.request("GET", path)
        return dict(result)

    async def search(
        self,
        body: Mapping[str, Any],
        *,
        index: str | None = None,
    ) -> dict[str, Any]:
        """Search an index and return the raw Elasticsearch response."""
        result = await self.request(
            "POST",
            f"/{self._encoded_index(index)}/_search",
            json_body=body,
        )
        return dict(result)

    async def get_document(
        self,
        document_id: str | int,
        *,
        index: str | None = None,
    ) -> dict[str, Any] | None:
        """Return a document source, or None when the document does not exist."""
        path = (
            f"/{self._encoded_index(index)}/_doc/"
            f"{quote(str(document_id), safe='')}"
        )
        try:
            result = await self.request("GET", path)
        except ElasticsearchRequestError as exc:
            if exc.status_code == 404:
                return None
            raise
        source = result.get("_source")
        return dict(source) if source is not None else None

    async def count(
        self,
        query: Mapping[str, Any] | None = None,
        *,
        index: str | None = None,
    ) -> int:
        """Count parent documents matching an optional query."""
        body = {"query": dict(query)} if query is not None else None
        result = await self.request(
            "POST",
            f"/{self._encoded_index(index)}/_count",
            json_body=body,
        )
        return int(result["count"])

    async def index_document(
        self,
        document_id: str | int,
        document: Mapping[str, Any],
        *,
        index: str | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Create or replace one document."""
        params = {"refresh": "wait_for"} if refresh else None
        result = await self.request(
            "PUT",
            (
                f"/{self._encoded_index(index)}/_doc/"
                f"{quote(str(document_id), safe='')}"
            ),
            params=params,
            json_body=document,
        )
        return dict(result)

    async def delete_document(
        self,
        document_id: str | int,
        *,
        index: str | None = None,
        refresh: bool = False,
    ) -> bool:
        """Delete one document and return False when it did not exist."""
        params = {"refresh": "wait_for"} if refresh else None
        try:
            await self.request(
                "DELETE",
                (
                    f"/{self._encoded_index(index)}/_doc/"
                    f"{quote(str(document_id), safe='')}"
                ),
                params=params,
            )
        except ElasticsearchRequestError as exc:
            if exc.status_code == 404:
                return False
            raise
        return True

    def _encoded_index(self, index: str | None) -> str:
        name = index or self.default_index
        if not name:
            raise ValueError("An Elasticsearch index name is required")
        return quote(name, safe="")

    @staticmethod
    def _error_reason(details: Any) -> str:
        if isinstance(details, dict):
            error = details.get("error")
            if isinstance(error, dict):
                return str(error.get("reason") or error.get("type") or error)
            if error is not None:
                return str(error)
        return str(details)[:2000]


elasticsearch = ElasticsearchClient(
    ELASTICSEARCH_URL,
    ELASTICSEARCH_INDEX,
    username=ELASTICSEARCH_USERNAME,
    password=ELASTICSEARCH_PASSWORD,
    timeout=ELASTICSEARCH_TIMEOUT_SECONDS,
)


def get_elasticsearch() -> ElasticsearchClient:
    """FastAPI dependency and service-level accessor for the shared client."""
    return elasticsearch
