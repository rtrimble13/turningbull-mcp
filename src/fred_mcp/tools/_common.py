"""Shared helpers for FRED tool modules."""

from __future__ import annotations

from typing import Any

from turningbull_mcp.models import OutputMode, ResponseFormat
from turningbull_mcp.tool_helpers import (
    READ_ONLY,
    render_large_result as _render_large,
    render_small_result,
    wrap_error,
)

from ..output import output_dir

__all__ = [
    "READ_ONLY",
    "get_client",
    "output_dir",
    "qp",
    "render_large_result",
    "render_small_result",
    "wrap_error",
]


def get_client():  # re-export for tools
    from ..client import get_client as _impl

    return _impl()


def qp(**kwargs: Any) -> dict[str, Any]:
    """Build a query-param dict, dropping ``None`` and unwrapping enums."""
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        out[key] = getattr(value, "value", value)
    return out


def render_large_result(
    rows: list[dict[str, Any]],
    *,
    name: str,
    mode: OutputMode,
    fmt: ResponseFormat,
    title: str,
    what: str,
) -> str:
    """FRED-flavored wrapper that injects the FRED output dir."""
    return _render_large(
        rows, name=name, mode=mode, fmt=fmt, output_dir=output_dir(), title=title, what=what
    )
