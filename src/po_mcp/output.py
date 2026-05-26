"""PO-flavored output-directory resolution.

Persisted artifacts (assets.json datasets, params files, optimization
results, frontier CSVs, Jupyter reports, walk-forward backtests, and
content-addressed temp data files materialized from inline JSON inputs)
live under ``$PO_OUTPUT_DIR`` in a fixed substructure so a PM/quant can
find every file produced by any tool.

Layout (created lazily on first use):

```
$PO_OUTPUT_DIR/
├── data/        assets.json datasets (from po_estimate_covariance or chained tools)
├── params/      optimization-params JSON (MVO constraints, BL views, …)
├── results/     single-portfolio optimization results (JSON)
├── frontiers/   efficient-frontier CSVs
├── reports/     Jupyter HTML + notebook from `po report`
├── backtests/   walk-forward equity curves, trades, summaries
└── tmp/         content-hashed JSON files materialized from inline data
```
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from turningbull_mcp.output import resolve_output_dir

SUBDIRS: tuple[str, ...] = (
    "data",
    "params",
    "results",
    "frontiers",
    "reports",
    "backtests",
    "tmp",
)


def output_dir() -> Path:
    """Resolve ``$PO_OUTPUT_DIR`` (defaulting to ``./po_output``)."""
    root = resolve_output_dir("PO_OUTPUT_DIR", "./po_output")
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def data_dir() -> Path:
    return output_dir() / "data"


def params_dir() -> Path:
    return output_dir() / "params"


def results_dir() -> Path:
    return output_dir() / "results"


def frontiers_dir() -> Path:
    return output_dir() / "frontiers"


def reports_dir() -> Path:
    return output_dir() / "reports"


def backtests_dir() -> Path:
    return output_dir() / "backtests"


def tmp_dir() -> Path:
    return output_dir() / "tmp"


def safe_filename(name: str) -> str:
    """Make ``name`` safe for use as a filename component."""
    keep = "-_.,()^"
    return "".join(c if c.isalnum() or c in keep else "_" for c in name)


def content_hash(blob: bytes | str) -> str:
    """SHA-1 of ``blob`` (utf-8 if str), first 12 hex chars."""
    if isinstance(blob, str):
        blob = blob.encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def label_or_hash(label: str | None, *parts: str) -> str:
    """Pick a filename stem: normalized label if non-empty, else a short
    content hash of ``parts``."""
    if label:
        cleaned = safe_filename(label)
        if cleaned:
            return cleaned
    return content_hash("|".join(parts))
