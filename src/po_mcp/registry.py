"""Lookup helpers for saved optimization-result JSONs.

The runner persists every CLI optimization result into
``$PO_OUTPUT_DIR/results/``; this module provides a thin, read-only
index so a PM can list what's been computed and load a specific result
by path.

The "registry" is just the filesystem — no database, no lock files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import POError
from .interpretation import extract_metrics, extract_weights
from .output import results_dir


def list_results() -> list[dict[str, Any]]:
    """Return one summary dict per JSON in ``$PO_OUTPUT_DIR/results/``."""
    out: list[dict[str, Any]] = []
    for path in sorted(results_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        weights = extract_weights(data) if isinstance(data, dict) else {}
        metrics = extract_metrics(data) if isinstance(data, dict) else {}
        entry: dict[str, Any] = {
            "path": str(path),
            "label": path.stem,
            "n_assets": len(weights),
            "top_holdings": _top_n(weights, n=5),
            "metrics": metrics,
            "created_at": _file_iso_mtime(path),
        }
        out.append(entry)
    return out


def load_result(path: str | Path) -> dict[str, Any]:
    """Read a saved result JSON and return the structured parse + raw doc."""
    p = Path(path).expanduser()
    if not p.exists():
        raise POError(f"result file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise POError(f"could not read result JSON at {p}: {exc}") from exc
    weights = extract_weights(data) if isinstance(data, dict) else {}
    metrics = extract_metrics(data) if isinstance(data, dict) else {}
    return {
        "path": str(p.resolve()),
        "label": p.stem,
        "weights": weights,
        "metrics": metrics,
        "raw_json": data,
    }


def _top_n(weights: dict[str, float], *, n: int) -> list[dict[str, Any]]:
    items = sorted(weights.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [{"ticker": t, "weight": w} for t, w in items[:n]]


def _file_iso_mtime(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
