"""Lookup helpers for saved model JSONs.

The runner persists every fitted model into ``$AG_OUTPUT_DIR/models/``;
this module provides a thin, read-only index so analysts can list what's
been fitted and load a specific model by path or label.

The "registry" is just the filesystem — no database, no lock files. Two
concurrent `ag fit` calls writing to different output paths Just Work;
two calls writing to the same path race normally.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import AGError
from .interpretation import parse_model_json
from .output import models_dir


def list_models() -> list[dict[str, Any]]:
    """Return one summary dict per JSON in ``$AG_OUTPUT_DIR/models/``.

    Each entry includes:
      - ``path`` — absolute path to the model JSON
      - ``label`` — the filename stem
      - ``spec`` — ``arima``, ``garch`` tuples if parsable
      - ``persistence`` — α+β derived from the saved params
      - ``log_likelihood``, ``aic``, ``bic`` — fit quality when present
      - ``created_at`` — ISO UTC timestamp of the file's mtime
    """
    out: list[dict[str, Any]] = []
    for path in sorted(models_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parsed = parse_model_json(data) if isinstance(data, dict) else {}
        entry: dict[str, Any] = {
            "path": str(path),
            "label": path.stem,
            "spec": {
                "arima": parsed.get("arima"),
                "garch": parsed.get("garch"),
                "innovation": parsed.get("distribution_used"),
            },
            "persistence": parsed.get("garch_persistence"),
            "near_unit_root": parsed.get("near_unit_root"),
            "log_likelihood": parsed.get("log_likelihood"),
            "aic": parsed.get("aic"),
            "bic": parsed.get("bic"),
            "converged": parsed.get("converged"),
            "created_at": _file_iso_mtime(path),
        }
        out.append(entry)
    return out


def load_model(path: str | Path) -> dict[str, Any]:
    """Read a saved model JSON and return the structured parse + raw doc."""
    p = Path(path).expanduser()
    if not p.exists():
        raise AGError(f"model file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AGError(f"could not read model JSON at {p}: {exc}") from exc
    parsed = parse_model_json(data) if isinstance(data, dict) else {}
    return {
        "path": str(p.resolve()),
        "label": p.stem,
        "model_json": data,
        **parsed,
    }


def _file_iso_mtime(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
