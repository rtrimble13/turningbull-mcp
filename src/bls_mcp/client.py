"""Async HTTP client for the BLS Public Data API.

Routes calls to v2 when ``BLS_API_KEY`` is set, falling back to v1 (no key,
tighter limits, single-series GETs) otherwise. Composes the shared
:mod:`turningbull_mcp.http` primitives for connection pooling and
exponential-backoff retry on 429/5xx.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from turningbull_mcp.config import get_env
from turningbull_mcp.http import (
    RETRYABLE_STATUSES,
    backoff_seconds,
    make_async_client as _make_shared_async_client,
)

from .errors import BLSError, map_http_error

V2_BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
V1_BASE_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

# Per-request caps documented by BLS.
V2_MAX_SERIES_PER_REQUEST = 50
V2_MAX_YEAR_SPAN = 20
V1_MAX_YEAR_SPAN = 10


class BLSClient:
    """Wraps httpx.AsyncClient with BLS-specific routing and retry."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def api_key(self) -> str | None:
        """Return the BLS API key from the environment, or ``None``."""
        return get_env("BLS_API_KEY")

    @property
    def using_v2(self) -> bool:
        return bool(self.api_key)

    async def fetch(
        self,
        series_ids: list[str],
        *,
        start_year: int | None = None,
        end_year: int | None = None,
        catalog: bool = False,
        calculations: bool = False,
        annual_average: bool = False,
        aspects: bool = False,
        retries: int = 3,
    ) -> list[dict[str, Any]]:
        """Fetch one or more series and return the raw ``Results.series`` list.

        Routes through v2 (POST JSON, multi-series) when a key is configured,
        otherwise falls back to v1 (single-series GET, fanned out and merged).
        The v1 path silently drops ``catalog``/``calculations``/
        ``annual_average``/``aspects`` because the endpoint doesn't support them.
        """
        if not series_ids:
            return []
        if self.using_v2:
            return await self._fetch_v2(
                series_ids,
                start_year=start_year,
                end_year=end_year,
                catalog=catalog,
                calculations=calculations,
                annual_average=annual_average,
                aspects=aspects,
                retries=retries,
            )
        return await self._fetch_v1(
            series_ids,
            start_year=start_year,
            end_year=end_year,
            retries=retries,
        )

    async def _fetch_v2(
        self,
        series_ids: list[str],
        *,
        start_year: int | None,
        end_year: int | None,
        catalog: bool,
        calculations: bool,
        annual_average: bool,
        aspects: bool,
        retries: int,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "seriesid": series_ids,
            "registrationkey": self.api_key,
        }
        if start_year is not None:
            body["startyear"] = str(start_year)
        if end_year is not None:
            body["endyear"] = str(end_year)
        if catalog:
            body["catalog"] = True
        if calculations:
            body["calculations"] = True
        if annual_average:
            body["annualaverage"] = True
        if aspects:
            body["aspects"] = True

        payload = await self._post(V2_BASE_URL, body, retries=retries)
        return self._extract_series(payload)

    async def _fetch_v1(
        self,
        series_ids: list[str],
        *,
        start_year: int | None,
        end_year: int | None,
        retries: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        params: dict[str, Any] = {}
        if start_year is not None:
            params["startyear"] = str(start_year)
        if end_year is not None:
            params["endyear"] = str(end_year)
        for sid in series_ids:
            url = f"{V1_BASE_URL}{sid}"
            payload = await self._get(url, params or None, retries=retries)
            merged.extend(self._extract_series(payload))
        return merged

    async def _post(
        self,
        url: str,
        body: dict[str, Any],
        *,
        retries: int,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await self._http.post(url, json=body)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_exc = map_http_error(exc)
                if exc.response.status_code in RETRYABLE_STATUSES and attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
            except httpx.RequestError as exc:
                last_exc = BLSError(f"BLS request failed: {exc!s}")
                if attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
        raise last_exc or BLSError("BLS request failed without an exception.")

    async def _get(
        self,
        url: str,
        params: dict[str, Any] | None,
        *,
        retries: int,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await self._http.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_exc = map_http_error(exc)
                if exc.response.status_code in RETRYABLE_STATUSES and attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
            except httpx.RequestError as exc:
                last_exc = BLSError(f"BLS request failed: {exc!s}")
                if attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
        raise last_exc or BLSError("BLS request failed without an exception.")

    @staticmethod
    def _extract_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate the BLS envelope and return ``Results.series``.

        Raises :class:`BLSError` whose message includes the API's ``message``
        array when ``status != "REQUEST_SUCCEEDED"`` so the model sees a real
        error instead of an empty result.
        """
        if not isinstance(payload, dict):
            raise BLSError(f"Unexpected BLS response shape: {type(payload).__name__}.")
        status = payload.get("status")
        if status != "REQUEST_SUCCEEDED":
            messages = payload.get("message") or []
            if isinstance(messages, list):
                msg_text = "; ".join(str(m) for m in messages) or "no detail"
            else:
                msg_text = str(messages)
            raise BLSError(
                f"BLS request failed (status={status!r}): {msg_text}"
            )
        results = payload.get("Results") or {}
        series = results.get("series") or []
        if not isinstance(series, list):
            raise BLSError("BLS response missing Results.series list.")
        return series


def make_async_client() -> httpx.AsyncClient:
    """Build the underlying httpx client. Lifespan owns its close.

    Spec calls for a 30s timeout; the shared factory's default (10s connect,
    60s read) is comfortably wider, so we trim it down to match the spec.
    """
    return _make_shared_async_client(
        user_agent="bls-mcp/0.1",
        connect_timeout=10.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )


_singleton: BLSClient | None = None


def install_client(client: BLSClient) -> None:
    """Register the BLSClient for tools to retrieve via :func:`get_client`."""
    global _singleton
    _singleton = client


def get_client() -> BLSClient:
    if _singleton is None:
        raise BLSError(
            "BLS client is not initialized. The server's lifespan failed to start."
        )
    return _singleton
