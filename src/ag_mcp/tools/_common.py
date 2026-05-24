"""AG-tool shared helpers.

Re-exports the connector-agnostic helpers from :mod:`turningbull_mcp.tool_helpers`
and wraps :func:`render_large_result` so the tool modules don't need to thread
the AG output directory through every call site.
"""

from __future__ import annotations

from turningbull_mcp.tool_helpers import (  # noqa: F401  (re-exports)
    READ_ONLY,
    render_small_result,
    wrap_error,
)
from turningbull_mcp.tool_helpers import (
    render_large_result as _shared_render_large_result,
)

from ..models import OutputMode, ResponseFormat
from ..output import output_dir


def render_large_result(
    rows: list[dict],
    *,
    name: str,
    mode: OutputMode,
    fmt: ResponseFormat,
    title: str | None = None,
    what: str | None = None,
) -> str:
    """AG wrapper around the shared helper that supplies ``$AG_OUTPUT_DIR``."""
    return _shared_render_large_result(
        rows,
        name=name,
        mode=mode,
        fmt=fmt,
        output_dir=output_dir(),
        title=title,
        what=what,
    )
