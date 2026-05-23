"""BLS-specific error helpers.

Inherits from the shared :class:`ConnectorError` base so the generic tool
wrapper formats it consistently with the rest of the repo.
"""

from __future__ import annotations

import httpx

from turningbull_mcp.errors import ConnectorError, empty_result_message  # noqa: F401


class BLSError(ConnectorError):
    """Surface-level BLS error returned to the caller as a tool result."""


def map_http_error(exc: httpx.HTTPStatusError) -> BLSError:
    status = exc.response.status_code
    url = str(exc.request.url).split("?", 1)[0]
    if status == 401:
        return BLSError(
            "Invalid BLS API key. Check the BLS_API_KEY env var, or unset it "
            "to use the v1 endpoint (no key, tighter limits)."
        )
    if status == 404:
        return BLSError(
            f"BLS endpoint not found: {url}. The series ID may not exist."
        )
    if status == 429:
        return BLSError(
            "BLS rate limit hit (500/day for v2, 25/day for v1). The server "
            "retried with backoff; try again later."
        )
    if 500 <= status < 600:
        return BLSError(f"BLS server error ({status}) at {url}. Retry later.")
    return BLSError(f"BLS HTTP error {status} at {url}.")
