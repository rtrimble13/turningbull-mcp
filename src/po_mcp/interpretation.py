"""Parsers for the `po` CLI output (JSON, CSV) and audit-trail.

The CLI always writes a structured artifact when invoked with ``-f json``
(single portfolio) or ``-f csv`` (frontier). We force one of those two
formats from the runner so we never have to scrape free-text from
``console`` output. The helpers below normalize that artifact into a
flat dict the tool layer can hand to ``render_small_result`` and
``render_large_result``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_result_json(path: Path) -> dict[str, Any]:
    """Read a `po`-emitted result JSON; raise ``FileNotFoundError`` if missing."""
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def read_csv_rows(path: Path, *, max_rows: int | None = None) -> list[dict[str, Any]]:
    """Read a small CSV without pulling pandas in for tiny outputs.

    Numeric fields are coerced to float; empty strings become ``None``.
    """
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                coerced: dict[str, Any] = {}
                for k, v in row.items():
                    if v is None:
                        coerced[k] = None
                        continue
                    s = v.strip()
                    if not s:
                        coerced[k] = None
                        continue
                    try:
                        coerced[k] = float(s)
                    except ValueError:
                        coerced[k] = s
                rows.append(coerced)
                if max_rows is not None and len(rows) >= max_rows:
                    break
    except (FileNotFoundError, OSError):
        return []
    return rows


def extract_weights(result_json: dict[str, Any]) -> dict[str, float]:
    """Return ``{ticker: weight}`` from a `po` result JSON.

    The JSON shape varies slightly by CLI version — try the common keys
    in order: ``weights`` (object), ``weights`` (list paired with
    ``assets``), top-level ``portfolio.weights``.
    """
    # Common shape: {"weights": {"AAPL": 0.4, "MSFT": 0.6}}
    w = result_json.get("weights")
    if isinstance(w, dict):
        return {str(k): float(v) for k, v in w.items()}
    # Alt shape: {"weights": [0.4, 0.6], "assets": [{"ticker": "AAPL"}, ...]}
    if isinstance(w, list):
        assets = result_json.get("assets") or []
        tickers = [str(a.get("ticker", f"asset_{i}")) for i, a in enumerate(assets)]
        if len(tickers) == len(w):
            return {t: float(v) for t, v in zip(tickers, w)}
        return {f"asset_{i}": float(v) for i, v in enumerate(w)}
    # Alt shape: {"portfolio": {"weights": {...}}}
    portfolio = result_json.get("portfolio")
    if isinstance(portfolio, dict):
        return extract_weights(portfolio)
    return {}


def extract_metrics(result_json: dict[str, Any]) -> dict[str, Any]:
    """Return portfolio metrics (return, vol, Sharpe, diversification, etc.)
    from a `po` result JSON.

    Looks under ``metrics`` first, then falls back to top-level keys.
    """
    metrics = result_json.get("metrics")
    if isinstance(metrics, dict):
        return dict(metrics)
    keys = (
        "expected_return",
        "volatility",
        "variance",
        "sharpe_ratio",
        "sharpe",
        "diversification_ratio",
        "effective_n",
        "tracking_error",
        "information_ratio",
        "active_share",
        "beta",
        "turnover",
        "max_position",
        "gross_exposure",
        "net_exposure",
    )
    return {k: result_json[k] for k in keys if k in result_json}


def extract_diagnostics(result_json: dict[str, Any]) -> dict[str, Any]:
    """Return solver/constraint diagnostics from a `po` result JSON.

    Tries common keys: ``diagnostics``, ``solver``, ``audit``,
    ``audit_trail``. Returns ``{}`` when none are present.
    """
    for key in ("diagnostics", "solver", "audit", "audit_trail"):
        v = result_json.get(key)
        if isinstance(v, (dict, list)) and v:
            return {key: v}
    return {}


def frontier_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the min-vol / max-Sharpe / max-return points from a frontier CSV.

    Tolerates column-name variation (``volatility`` vs ``vol`` vs ``risk``).
    Returns ``{}`` when columns can't be inferred.
    """
    if not rows:
        return {}

    def col(*names: str) -> str | None:
        for name in names:
            for k in rows[0].keys():
                if k.lower() == name:
                    return k
        return None

    vol_key = col("volatility", "vol", "risk", "sigma")
    ret_key = col("expected_return", "return", "mu")
    shp_key = col("sharpe", "sharpe_ratio")
    if not vol_key or not ret_key:
        return {}

    def numeric(rows_in: list[dict[str, Any]], key: str) -> list[float]:
        out: list[float] = []
        for r in rows_in:
            v = r.get(key)
            try:
                out.append(float(v) if v is not None else float("nan"))
            except (TypeError, ValueError):
                out.append(float("nan"))
        return out

    vols = numeric(rows, vol_key)
    rets = numeric(rows, ret_key)
    shps = numeric(rows, shp_key) if shp_key else [r / v if v else float("nan") for r, v in zip(rets, vols)]

    def best(xs: list[float], *, maximize: bool) -> int | None:
        idx = None
        best_val = float("-inf") if maximize else float("inf")
        for i, x in enumerate(xs):
            if x != x:  # NaN
                continue
            if (maximize and x > best_val) or (not maximize and x < best_val):
                best_val = x
                idx = i
        return idx

    summary: dict[str, Any] = {"n_points": len(rows)}
    i_minvol = best(vols, maximize=False)
    i_maxret = best(rets, maximize=True)
    i_maxshp = best(shps, maximize=True)
    if i_minvol is not None:
        summary["min_volatility"] = rows[i_minvol]
    if i_maxret is not None:
        summary["max_return"] = rows[i_maxret]
    if i_maxshp is not None:
        summary["max_sharpe"] = rows[i_maxshp]
    return summary
