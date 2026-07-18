"""Reusable asynchronous Qdrant client for vector search (RAG chính sách).

Cùng phong cách với db/elasticsearch.py: một httpx pool dùng chung, gọi thẳng
REST API của Qdrant (không dùng SDK) để giữ dependency tối thiểu.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from app.config import (
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_TIMEOUT_SECONDS,
    QDRANT_URL,
)


class QdrantRequestError(RuntimeError):
    """A Qdrant request failed or returned a non-success response."""

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


class QdrantClient:
    """Small HTTP client with one shared async connection pool."""

    def __init__(
        self,
        base_url: str,
        default_collection: str,
        *,
        api_key: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_collection = default_collection
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._start_lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._client is not None and not self._client.is_closed

    async def start(self) -> QdrantClient:
        """Create the connection pool if it has not been created yet."""
        if self.is_started:
            return self
        async with self._start_lock:
            if self.is_started:
                return self
            headers = {
                "Accept": "application/json",
                "User-Agent": "dmx-advisor-be1/1.0",
            }
            if self.api_key:
                headers["api-key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                headers=headers,
            )
        return self

    async def close(self) -> None:
        """Close the connection pool."""
        async with self._start_lock:
            client = self._client
            self._client = None
            if client is not None and not client.is_closed:
                await client.aclose()

    async def __aenter__(self) -> QdrantClient:
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
        expected: tuple[int, ...] = (),
    ) -> Any:
        """Perform a JSON request against a Qdrant API path.

        `expected`: status codes coi là hợp lệ dù is_error (vd 404 khi kiểm tra tồn tại).
        """
        if not path.startswith("/"):
            raise ValueError("Qdrant request paths must start with '/'")
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
            raise QdrantRequestError(
                f"Qdrant request failed: {method.upper()} {path}: {exc}"
            ) from exc

        if response.is_error and response.status_code not in expected:
            try:
                details: Any = response.json()
            except ValueError:
                details = response.text[:2000]
            raise QdrantRequestError(
                f"Qdrant returned HTTP {response.status_code} for {method.upper()} {path}",
                status_code=response.status_code,
                details=details,
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise QdrantRequestError(
                f"Qdrant returned invalid JSON for {method.upper()} {path}",
                status_code=response.status_code,
                details=response.text[:2000],
            ) from exc

    async def ping(self) -> bool:
        """Return whether Qdrant is reachable."""
        try:
            await self.request("GET", "/")
        except QdrantRequestError:
            return False
        return True

    async def collection_exists(self, *, collection: str | None = None) -> bool:
        result = await self.request(
            "GET", f"/collections/{self._encoded(collection)}", expected=(404,)
        )
        return bool(result and result.get("status") == "ok")

    async def recreate_collection(
        self,
        vector_size: int,
        *,
        collection: str | None = None,
        distance: str = "Cosine",
    ) -> None:
        """Xoá (nếu có) rồi tạo lại collection — dùng khi rebuild index."""
        name = self._encoded(collection)
        await self.request("DELETE", f"/collections/{name}", expected=(404,))
        await self.request(
            "PUT",
            f"/collections/{name}",
            json_body={"vectors": {"size": vector_size, "distance": distance}},
        )

    async def upsert(
        self,
        points: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
        wait: bool = True,
    ) -> None:
        """points: list {id, vector, payload}."""
        await self.request(
            "PUT",
            f"/collections/{self._encoded(collection)}/points",
            params={"wait": "true"} if wait else None,
            json_body={"points": [dict(p) for p in points]},
        )

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        collection: str | None = None,
    ) -> list[dict[str, Any]]:
        """Trả về list {id, score, payload} theo cosine giảm dần."""
        result = await self.request(
            "POST",
            f"/collections/{self._encoded(collection)}/points/search",
            json_body={"vector": list(vector), "limit": limit, "with_payload": True},
        )
        return list(result.get("result", [])) if result else []

    async def count(self, *, collection: str | None = None) -> int:
        result = await self.request(
            "POST",
            f"/collections/{self._encoded(collection)}/points/count",
            json_body={"exact": True},
            expected=(404,),
        )
        if not result or "result" not in result:
            return 0
        return int(result["result"]["count"])

    def _encoded(self, collection: str | None) -> str:
        name = collection or self.default_collection
        if not name:
            raise ValueError("A Qdrant collection name is required")
        return quote(name, safe="")


qdrant = QdrantClient(
    QDRANT_URL,
    QDRANT_COLLECTION,
    api_key=QDRANT_API_KEY,
    timeout=QDRANT_TIMEOUT_SECONDS,
)


def get_qdrant() -> QdrantClient:
    """FastAPI dependency and service-level accessor for the shared client."""
    return qdrant
