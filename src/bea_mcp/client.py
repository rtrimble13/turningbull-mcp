"""Async HTTP client for the BEA Data API.

BEA exposes a single GET endpoint that dispatches on ``method`` and
``DataSetName``. The client injects ``UserID`` + ``ResultFormat=JSON``,
retries on 429/5xx (honoring BEA's ``Retry-After`` header when present),
and validates the BEA envelope. Errors arrive two ways — HTTP status
codes and a ``Results.Error`` block inside an HTTP-200 response — both
funnel into :class:`BEAError`.
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

from .errors import BEAError, map_http_error

BASE_URL = "https://apps.bea.gov/api/data"


class BEAClient:
    """Wraps ``httpx.AsyncClient`` with BEA-specific auth and retry."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def api_key(self) -> str | None:
        """Return the BEA UserID (API key) from the environment, or ``None``."""
        return get_env("BEA_API_KEY")

    def _require_key(self) -> str:
        key = self.api_key
        if not key:
            raise BEAError(
                "BEA_API_KEY is not set. Register for a free 36-char UserID "
                "at https://apps.bea.gov/API/signup/ and add it to your .env "
                "file as BEA_API_KEY=<your key>."
            )
        return key

    async def call(
        self,
        method: str,
        *,
        dataset: str | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """Run a single BEA API call.

        - ``method`` — one of ``GetDataSetList``, ``GetParameterList``,
          ``GetParameterValues``, ``GetParameterValuesFiltered``, ``GetData``.
        - ``dataset`` — required for every method except ``GetDataSetList``.
        - ``params`` — dataset-specific parameters (e.g. ``TableName``,
          ``Frequency``, ``Year``); merged into the query.

        Returns the validated ``BEAAPI.Results`` payload.
        """
        query: dict[str, Any] = {
            "UserID": self._require_key(),
            "method": method,
            "ResultFormat": "JSON",
        }
        if dataset is not None:
            query["DataSetName"] = dataset
        if params:
            for k, v in params.items():
                if v is None or v == "":
                    continue
                if isinstance(v, (list, tuple)):
                    v = ",".join(str(item) for item in v)
                query[k] = v
        payload = await self._get(BASE_URL, query, retries=retries)
        return self._extract_results(payload)

    async def _get(
        self,
        url: str,
        params: dict[str, Any],
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
                status = exc.response.status_code
                if status in RETRYABLE_STATUSES and attempt < retries:
                    await asyncio.sleep(self._sleep_for(exc.response, attempt))
                    continue
                raise last_exc from exc
            except httpx.RequestError as exc:
                last_exc = BEAError(f"BEA request failed: {exc!s}")
                if attempt < retries:
                    await asyncio.sleep(backoff_seconds(attempt))
                    continue
                raise last_exc from exc
        raise last_exc or BEAError("BEA request failed without an exception.")

    @staticmethod
    def _sleep_for(response: httpx.Response, attempt: int) -> float:
        """Honor a Retry-After header when present; otherwise exp backoff.

        BEA's docs explicitly use ``Retry-After`` for 429s. The header is
        the authoritative value; we still ``max`` it with our usual backoff
        so a tiny value doesn't cause an immediate retry storm.
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), backoff_seconds(attempt))
            except (TypeError, ValueError):
                pass
        return backoff_seconds(attempt)

    @staticmethod
    def _extract_results(payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the ``BEAAPI`` envelope and return ``Results``.

        BEA returns errors with HTTP 200, signalling them with either:
        - ``Results.Error`` (object) — most common, e.g. invalid params.
        - ``Results`` itself being a list with an ``Error`` entry — older
          variant from some methods.

        Both shapes raise :class:`BEAError` with the API's own message so
        the caller sees a real error rather than an empty result.
        """
        if not isinstance(payload, dict):
            raise BEAError(f"Unexpected BEA response shape: {type(payload).__name__}.")
        envelope = payload.get("BEAAPI")
        if not isinstance(envelope, dict):
            raise BEAError("BEA response missing top-level 'BEAAPI' object.")
        results = envelope.get("Results")
        if results is None:
            error = envelope.get("Error")
            if error:
                raise BEAError(BEAClient._format_error(error))
            raise BEAError("BEA response missing 'Results'.")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and "Error" in item:
                    raise BEAError(BEAClient._format_error(item["Error"]))
            return {"_list": results}
        if isinstance(results, dict):
            err = results.get("Error")
            if err:
                raise BEAError(BEAClient._format_error(err))
            return results
        raise BEAError(f"Unexpected 'Results' shape: {type(results).__name__}.")

    @staticmethod
    def _format_error(error: Any) -> str:
        if isinstance(error, dict):
            code = error.get("APIErrorCode") or error.get("ErrorCode") or "?"
            desc = (
                error.get("APIErrorDescription")
                or error.get("ErrorDetail")
                or error.get("ErrorDescription")
                or "no detail"
            )
            return f"BEA API error {code}: {desc}"
        if isinstance(error, list):
            parts = [BEAClient._format_error(e) for e in error]
            return "; ".join(parts) or "BEA API error: no detail"
        return f"BEA API error: {error}"


def make_async_client() -> httpx.AsyncClient:
    """Build the underlying httpx client. Lifespan owns its close.

    BEA NIPA tables can return several MB; we keep the shared default 60s
    read timeout (don't narrow it).
    """
    return _make_shared_async_client(
        user_agent="bea-mcp/0.1",
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=30.0,
    )


_singleton: BEAClient | None = None


def install_client(client: BEAClient | None) -> None:
    """Register the BEAClient for tools to retrieve via :func:`get_client`."""
    global _singleton
    _singleton = client


def get_client() -> BEAClient:
    if _singleton is None:
        raise BEAError(
            "BEA client is not initialized. The server's lifespan failed to start."
        )
    return _singleton
