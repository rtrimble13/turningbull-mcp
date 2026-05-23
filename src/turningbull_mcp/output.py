"""Large-dataset file output (CSV + Parquet) for connector tools.

A tool that produces a potentially-large result calls :func:`write_dataset`
with its own ``output_dir`` and returns the resulting summary dict to the
caller, who avoids loading the full payload into context.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def resolve_output_dir(env_var: str, default: str) -> Path:
    """Return an existing, mkdir-ed Path from ``$env_var`` or ``default``.

    Each connector calls this with its own namespaced env var (e.g.
    ``FMP_OUTPUT_DIR``) and a sensible default. The resulting directory is
    passed to :func:`write_dataset`.
    """
    p = Path(os.environ.get(env_var, default)).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_dataset(
    rows: list[dict],
    *,
    name: str,
    output_dir: Path,
    formats: tuple[str, ...] = ("parquet", "csv"),
    head: int = 5,
    tail: int = 5,
) -> dict[str, Any]:
    """Write ``rows`` to ``output_dir`` and return a summary for the caller.

    The summary contains absolute file paths, row count, column list, the
    date range when a ``date`` column is present, and small head/tail previews.
    """
    if not rows:
        return {
            "row_count": 0,
            "files": [],
            "columns": [],
            "preview": {"head": [], "tail": []},
            "note": "no rows to write",
        }

    df = pd.DataFrame(rows)
    safe_name = _safe_name(name)
    written: list[str] = []
    if "parquet" in formats:
        path = output_dir / f"{safe_name}.parquet"
        df.to_parquet(path, index=False)
        written.append(str(path))
    if "csv" in formats:
        path = output_dir / f"{safe_name}.csv"
        df.to_csv(path, index=False)
        written.append(str(path))

    summary: dict[str, Any] = {
        "row_count": int(len(df)),
        "columns": list(df.columns),
        "files": written,
        "preview": {
            "head": _json_safe(df.head(head).to_dict(orient="records")),
            "tail": _json_safe(df.tail(tail).to_dict(orient="records")),
        },
    }
    if "date" in df.columns:
        try:
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if len(dates):
                summary["date_range"] = {
                    "from": str(dates.min().date()),
                    "to": str(dates.max().date()),
                }
        except Exception:
            pass
    return summary


INLINE_ROW_CAP = 5000


def inline_payload(rows: list[dict]) -> dict[str, Any]:
    """Return the full rows inline, capped to avoid runaway context."""
    if len(rows) > INLINE_ROW_CAP:
        return {
            "row_count": len(rows),
            "capped_at": INLINE_ROW_CAP,
            "rows": rows[:INLINE_ROW_CAP],
            "note": (
                f"inline output capped at {INLINE_ROW_CAP} rows; "
                "switch to mode=summary to receive the full dataset as files."
            ),
        }
    return {"row_count": len(rows), "rows": rows}


def _safe_name(name: str) -> str:
    keep = "-_.,()^"
    return "".join(c if c.isalnum() or c in keep else "_" for c in name)


def _json_safe(obj: Any) -> Any:
    """Ensure objects round-trip through json.dumps cleanly."""
    return json.loads(json.dumps(obj, default=str))
