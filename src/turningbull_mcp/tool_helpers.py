"""Shared helpers for connector tool modules.

These are connector-agnostic: read-only annotations, date-window chunking,
inline/summary rendering for large datasets, and error wrapping for the
common :class:`turningbull_mcp.errors.ConnectorError` base.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

from .errors import ConnectorError, empty_result_message
from .formatting import render
from .models import OutputMode, ResponseFormat
from .output import inline_payload, write_dataset

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def chunk_date_range(
    start: str, end: str, max_days: int
) -> list[tuple[str, str]]:
    """Split ``[start, end]`` into sequential ``<= max_days`` windows.

    Useful for APIs that cap historical pulls (e.g. FMP's ~5y cap).
    """
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if e <= s:
        return [(start, end)]
    chunks: list[tuple[str, str]] = []
    cursor = s
    while cursor < e:
        chunk_end = min(cursor + timedelta(days=max_days - 1), e)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def dedupe_by_date(rows: list[dict]) -> list[dict]:
    """Deduplicate rows by their ``date`` field, then sort ascending."""
    seen: set[str] = set()
    unique: list[dict] = []
    for r in rows:
        key = str(r.get("date"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    unique.sort(key=lambda r: str(r.get("date")))
    return unique


def wrap_error(exc: Exception) -> str:
    """Format an exception as a user-visible markdown error.

    Subclasses of :class:`ConnectorError` are rendered as the connector's
    own error; everything else is labelled "Unexpected error".
    """
    if isinstance(exc, ConnectorError):
        return f"**{type(exc).__name__}.** {exc}"
    return f"**Unexpected error.** {type(exc).__name__}: {exc}"


def render_small_result(
    data: Any,
    fmt: ResponseFormat,
    *,
    title: str | None = None,
    what: str | None = None,
) -> str:
    """Render a small result (single object or short list) inline."""
    if data is None or (isinstance(data, list) and not data):
        return empty_result_message(what or "this request")
    return render(data, fmt, title=title)


def render_large_result(
    rows: list[dict],
    *,
    name: str,
    mode: OutputMode,
    fmt: ResponseFormat,
    output_dir: Path,
    title: str | None = None,
    what: str | None = None,
) -> str:
    """Render a potentially-large list result honoring mode + format.

    ``output_dir`` is where ``mode=summary`` writes its CSV+Parquet files;
    each connector supplies its own (e.g. ``$FMP_OUTPUT_DIR``).
    """
    if not rows:
        return empty_result_message(what or name)
    if mode == OutputMode.inline:
        return render(inline_payload(rows), fmt, title=title)
    summary = write_dataset(rows, name=name, output_dir=output_dir)
    return render(summary, fmt, title=title or f"{name} (summary)")
