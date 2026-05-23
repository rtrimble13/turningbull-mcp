"""FMP-tool shared helpers.

Re-exports the connector-agnostic helpers from :mod:`turningbull_mcp.tool_helpers`
and wraps :func:`render_large_result` so the tool modules don't need to thread
the FMP output directory through every call site.
"""

from __future__ import annotations

from turningbull_mcp.tool_helpers import (  # noqa: F401  (re-exports)
    READ_ONLY,
    dedupe_by_date,
    render_small_result,
    wrap_error,
)
from turningbull_mcp.tool_helpers import (
    chunk_date_range as _shared_chunk_date_range,
    render_large_result as _shared_render_large_result,
)

from ..models import OutputMode, ResponseFormat
from ..output import output_dir

# Stay safely below the FMP ~5-year per-request cap for historical pulls.
CHUNK_DAYS = 5 * 365 - 30


def chunk_date_range(
    start: str, end: str, max_days: int = CHUNK_DAYS
) -> list[tuple[str, str]]:
    """Chunk a date range using the FMP default cap (~5 years)."""
    return _shared_chunk_date_range(start, end, max_days)


def render_large_result(
    rows: list[dict],
    *,
    name: str,
    mode: OutputMode,
    fmt: ResponseFormat,
    title: str | None = None,
    what: str | None = None,
) -> str:
    """FMP wrapper around the shared helper that supplies ``$FMP_OUTPUT_DIR``."""
    return _shared_render_large_result(
        rows,
        name=name,
        mode=mode,
        fmt=fmt,
        output_dir=output_dir(),
        title=title,
        what=what,
    )
