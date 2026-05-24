"""BEA-flavored dataset output.

Wraps the shared :mod:`turningbull_mcp.output` writer so callers don't need
to thread ``BEA_OUTPUT_DIR`` through every call site.
"""

from __future__ import annotations

from pathlib import Path

from turningbull_mcp.output import (  # noqa: F401  (re-exports for back-compat)
    INLINE_ROW_CAP,
    inline_payload,
    resolve_output_dir,
)
from turningbull_mcp.output import write_dataset as _shared_write_dataset


def output_dir() -> Path:
    """Resolve the BEA-specific output directory (``$BEA_OUTPUT_DIR``)."""
    return resolve_output_dir("BEA_OUTPUT_DIR", "./bea_output")


def write_dataset(rows: list[dict], *, name: str, **kwargs) -> dict:
    """Write a dataset under :func:`output_dir`. See shared writer for kwargs."""
    return _shared_write_dataset(rows, name=name, output_dir=output_dir(), **kwargs)
