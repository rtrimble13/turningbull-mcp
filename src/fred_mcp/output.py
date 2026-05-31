"""FRED output-dir resolver and dataset writer wrapper."""

from __future__ import annotations

from typing import Any

from turningbull_mcp.output import resolve_output_dir, write_dataset as _write


def output_dir() -> Any:
    return resolve_output_dir("FRED_OUTPUT_DIR", "./fred_output")


def write_dataset(rows: list[dict[str, Any]], *, name: str, **kwargs: Any) -> Any:
    return _write(rows, name=name, output_dir=output_dir(), **kwargs)
