"""Error types and HTTP status mapping for the FRED connector."""

from __future__ import annotations

import httpx

from turningbull_mcp.errors import ConnectorError


class FredError(ConnectorError):
    """Raised when the FRED API returns an error or is misconfigured."""


def map_http_error(exc: httpx.HTTPStatusError) -> FredError:
    """Translate an httpx status error into a friendly FredError.

    FRED returns a JSON body of the form ``{"error_code": ..., "error_message":
    ...}`` on failures, so we surface that message when available.
    """
    status = exc.response.status_code
    detail = ""
    try:
        body = exc.response.json()
        if isinstance(body, dict):
            detail = str(body.get("error_message") or "")
    except Exception:  # noqa: BLE001 - body may not be JSON
        detail = ""

    if status == 400:
        hint = detail or "Check the request parameters and FRED_API_KEY."
        return FredError(f"FRED rejected the request (400). {hint}")
    if status in (401, 403):
        return FredError("FRED rejected the request (check FRED_API_KEY).")
    if status == 404:
        return FredError("FRED endpoint or resource not found (404).")
    if status == 429:
        return FredError("FRED rate limit hit (429). Try again shortly.")
    if status >= 500:
        return FredError(f"FRED server error ({status}). Try again later.")
    return FredError(f"FRED request failed ({status}).{(' ' + detail) if detail else ''}")
