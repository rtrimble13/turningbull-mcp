"""BEA-specific error helpers.

Inherits from the shared :class:`ConnectorError` base so the generic tool
wrapper formats it consistently with the rest of the repo. BEA returns
errors two ways: ordinary HTTP status codes (401/404/429/5xx) and an
in-envelope ``Results.Error`` block on HTTP 200; both paths funnel into
:class:`BEAError`.
"""

from __future__ import annotations

import httpx

from turningbull_mcp.errors import ConnectorError, empty_result_message  # noqa: F401


class BEAError(ConnectorError):
    """Surface-level BEA error returned to the caller as a tool result."""


def map_http_error(exc: httpx.HTTPStatusError) -> BEAError:
    status = exc.response.status_code
    url = str(exc.request.url).split("?", 1)[0]
    if status in (401, 403):
        return BEAError(
            "Invalid or missing BEA UserID. Set BEA_API_KEY in your .env "
            "(register a free 36-char key at https://apps.bea.gov/API/signup/)."
        )
    if status == 404:
        return BEAError(
            f"BEA endpoint not found: {url}. The dataset name may be wrong."
        )
    if status == 429:
        retry_after = exc.response.headers.get("Retry-After")
        suffix = f" Retry-After: {retry_after}s." if retry_after else ""
        return BEAError(
            "BEA rate limit hit (100 requests/min, 100MB/min, 30 errors/min)."
            + suffix
            + " The server retried with backoff; try again later."
        )
    if 500 <= status < 600:
        return BEAError(f"BEA server error ({status}) at {url}. Retry later.")
    return BEAError(f"BEA HTTP error {status} at {url}.")
