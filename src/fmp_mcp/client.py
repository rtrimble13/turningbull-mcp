"""Shared async HTTP client for the FMP stable API.

Composes the shared :mod:`turningbull_mcp.http` primitives (httpx client
factory, exponential-backoff helper) with FMP-specific behavior: ``apikey``
query-param injection and FMP error-envelope detection.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from turningbull_mcp.config import require_env
from turningbull_mcp.http import (
    RETRYABLE_STATUSES,
    backoff_seconds,
    make_async_client as _make_shared_async_client,
)

from .errors import FMPError, map_http_error

BASE_URL = "https://financialmodelingprep.com"


def _api_key() -> str:
    try:
        return require_env(
            "FMP_API_KEY",
            hint="Add it to your repo-root .env file or your shell environment.",
        )
    except RuntimeError as exc:
        raise FMPError(str(exc)) from exc


class FMPClient:
    """Thin wrapper around httpx.AsyncClient with FMP-specific behavior."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retries: int = 3,
    ) -> Any:
        """GET an FMP path and return parsed JSON.

        - ``path`` is the path component starting with ``/`` (e.g.
          ``/stable/quote``) or ``/api/v3/...`` for legacy endpoints.
        - ``params`` are query params; ``None`` values are dropped.
        - Injects ``apikey``. Retries 429/5xx with exponential backoff + jitter.
        """
        clean_params: dict[str, Any] = {"apikey": _api_key()}
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                if isinstance(v, bool):
                    clean_params[k] = "true" if v else "false"
                else:
                    clean_params[k] = v

        url = f"{BASE_URL}{path}"
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await self._http.get(url, params=clean_params)
                if response.status_code in RETRYABLE_STATUSES:
                    response.raise_for_status()
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "Error Message" in data:
                    raise FMPError(f"FMP API error: {data['Error Message']}")
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = map_http_error(exc)
                status = exc.response.status_code
                if status in RETRYABLE_STATUSES and attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
            except httpx.RequestError as exc:
                last_exc = FMPError(f"FMP request failed: {exc!s}")
                if attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
        raise last_exc or FMPError("FMP request failed without an exception.")


def make_async_client() -> httpx.AsyncClient:
    """Build the underlying httpx client. Lifespan owns its close."""
    return _make_shared_async_client(user_agent="fmp-mcp/0.1")


_singleton: FMPClient | None = None


def install_client(client: FMPClient) -> None:
    """Register the FMPClient for tools to retrieve via :func:`get_client`."""
    global _singleton
    _singleton = client


def get_client() -> FMPClient:
    if _singleton is None:
        raise FMPError(
            "FMP client is not initialized. The server's lifespan failed to start."
        )
    return _singleton


def log_stderr(msg: str) -> None:
    """Back-compat re-export. Prefer :func:`turningbull_mcp.logging.log_stderr`."""
    from turningbull_mcp.logging import log_stderr as _log

    _log(msg)
