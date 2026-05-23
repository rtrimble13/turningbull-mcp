"""FMP-specific error helpers.

Maps HTTP failures from the FMP API to actionable, FMP-flavored messages.
Inherits from the shared :class:`ConnectorError` base so the generic tool
wrapper formats it consistently.
"""

from __future__ import annotations

import httpx

from turningbull_mcp.errors import ConnectorError, empty_result_message  # noqa: F401


class FMPError(ConnectorError):
    """Surface-level FMP error returned to the caller as a tool result."""


def map_http_error(exc: httpx.HTTPStatusError) -> FMPError:
    status = exc.response.status_code
    url = str(exc.request.url).split("?", 1)[0]
    if status == 401:
        return FMPError(
            "Invalid or missing FMP API key. Check the FMP_API_KEY env var."
        )
    if status == 403:
        return FMPError(
            "This FMP endpoint requires a higher plan tier than your key allows."
        )
    if status == 404:
        return FMPError(
            f"FMP endpoint or symbol not found: {url}. "
            "Verify the ticker spelling and the endpoint path."
        )
    if status == 429:
        return FMPError(
            "FMP rate limit hit. The server retried with backoff; "
            "try again shortly."
        )
    if 500 <= status < 600:
        return FMPError(
            f"FMP server error ({status}) at {url}. Retry later."
        )
    return FMPError(f"FMP HTTP error {status} at {url}.")
