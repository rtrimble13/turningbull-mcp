"""Async HTTP client for the St. Louis Fed FRED API (and GeoFRED maps)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from turningbull_mcp.http import (
    RETRYABLE_STATUSES,
    backoff_seconds,
    make_async_client as _make_shared_async_client,
)

from .errors import FredError, map_http_error

_FRED_BASE = "https://api.stlouisfed.org/fred"
_GEOFRED_BASE = "https://api.stlouisfed.org/geofred"

_client: FredClient | None = None


class FredClient:
    """Thin async wrapper over the FRED and GeoFRED endpoints.

    Every request needs an ``api_key`` and ``file_type=json``; these are
    injected automatically. FRED rejects keyless requests, so a missing key
    raises a clear :class:`FredError` before any network call is attempted.
    """

    def __init__(self, http: httpx.AsyncClient, *, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        return self._api_key

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        base: str = _FRED_BASE,
        retries: int = 3,
    ) -> Any:
        """GET ``path`` with ``params``; inject the key, retry on 429/5xx."""
        if not self._api_key:
            raise FredError(
                "FRED_API_KEY is required for FRED API requests. Get a free key "
                "at https://fredaccount.stlouisfed.org/apikeys"
            )
        query: dict[str, Any] = {k: v for k, v in (params or {}).items() if v is not None}
        query["api_key"] = self._api_key
        query["file_type"] = "json"
        url = f"{base}{path}"

        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await self._http.get(url, params=query)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in RETRYABLE_STATUSES and attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    last_exc = exc
                    continue
                raise map_http_error(exc) from exc
            except httpx.RequestError as exc:
                if attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    last_exc = exc
                    continue
                raise FredError(f"Network error contacting FRED: {exc}") from exc
        if last_exc is not None:
            raise FredError(str(last_exc))
        raise FredError("Unknown error contacting FRED")

    async def geo_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retries: int = 3,
    ) -> Any:
        """GET a GeoFRED (maps) ``path`` on the geofred host."""
        return await self.get(path, params, base=_GEOFRED_BASE, retries=retries)


def make_async_client() -> httpx.AsyncClient:
    """Build the underlying httpx client. Lifespan owns its close."""
    return _make_shared_async_client(user_agent="fred-mcp/0.1")


def install_client(client: FredClient) -> None:
    global _client
    _client = client


def get_client() -> FredClient:
    if _client is None:
        raise FredError("FRED client is not initialised")
    return _client
