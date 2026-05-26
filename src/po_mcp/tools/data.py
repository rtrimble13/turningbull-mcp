"""Data-preparation and utility tools.

These tools sit alongside the optimizer wrappers in :mod:`primitives`
and :mod:`portfolios`. They cover:

- ``po_estimate_covariance`` — turn a periodic-returns CSV into an
  ``assets.json``-shaped file (via portopt's shrinkage estimators) that
  any downstream tool can take as input.
- ``po_summarize_portfolio`` — arbitrary-weights performance metrics:
  expected return, volatility, Sharpe, diversification ratio, effective
  N, beta-vs-benchmark, tracking error, active share.
- ``po_validate_data`` — schema + PSD-covariance sanity check before
  paying for an optimization run.
- ``po_list_results`` / ``po_describe_result`` — registry of every
  persisted optimization result under ``$PO_OUTPUT_DIR/results/``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import pyengine, registry
from ..errors import POError
from ..models import (
    AssetDataInline,
    Label,
    ResponseFormat,
    Shrinkage,
    materialize_data,
)
from ..output import data_dir, label_or_hash, output_dir
from ._common import READ_ONLY, render_small_result, wrap_error


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="po_estimate_covariance",
        annotations=READ_ONLY,
        description=(
            "Estimate μ and Σ from a periodic-returns CSV (rows = periods, "
            "columns = tickers; first column may be a date label). Writes "
            "an assets.json-shaped JSON to $PO_OUTPUT_DIR/data/ and returns "
            "its path so downstream tools (po_mvo, po_max_sharpe, …) can "
            "chain off it. Shrinkage estimators: 'none', 'linear' (with "
            "shrinkage_delta), 'ledoit-wolf' (recommended for short "
            "samples), 'oas'. Requires `portopt`."
        ),
    )
    async def po_estimate_covariance(
        returns_csv_path: Annotated[
            str,
            Field(description="Path to a periodic-returns CSV."),
        ],
        periods_per_year: Annotated[
            int,
            Field(
                description="Annualization factor (252 daily, 12 monthly, 4 quarterly).",
                ge=1,
            ),
        ] = 252,
        shrinkage: Annotated[
            Shrinkage,
            Field(description="Covariance shrinkage estimator."),
        ] = Shrinkage.ledoit_wolf,
        shrinkage_delta: Annotated[
            float,
            Field(description="δ for shrinkage='linear'.", ge=0.0, le=1.0),
        ] = 0.2,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            path = Path(returns_csv_path).expanduser()
            if not path.exists():
                raise POError(f"returns CSV not found: {path}")
            estimated = pyengine.estimate_from_returns(
                path,
                periods_per_year=periods_per_year,
                shrinkage=shrinkage.value,
                shrinkage_delta=shrinkage_delta,
            )
            stem = label_or_hash(label, "estimated", path.name, shrinkage.value)
            out_path = data_dir() / f"{stem}.json"
            out_path.write_text(json.dumps(estimated, indent=2, default=str), encoding="utf-8")
            n_assets = len(estimated.get("assets", []))
            payload = {
                "data_path": str(out_path),
                "shrinkage": shrinkage.value,
                "periods_per_year": periods_per_year,
                "n_assets": n_assets,
                "tickers": [a.get("ticker") for a in estimated.get("assets", [])],
                "preview": {
                    "expected_returns": [
                        a.get("expected_return")
                        for a in estimated.get("assets", [])[:8]
                    ],
                },
                "artifacts": {"assets_json": str(out_path)},
            }
            return render_small_result(
                payload, response_format, title="po estimate-covariance",
                what="po_estimate_covariance",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_summarize_portfolio",
        annotations=READ_ONLY,
        description=(
            "Compute portfolio-level metrics for an arbitrary set of "
            "weights against a covariance matrix (and optionally μ, "
            "benchmark weights). Returns expected return, volatility, "
            "Sharpe, diversification ratio, effective N, active share, "
            "tracking error, beta-vs-benchmark, and per-asset risk "
            "contributions. The covariance and (optional) expected returns "
            "are read from inline `data` or `data_path`."
        ),
    )
    async def po_summarize_portfolio(
        weights: Annotated[
            dict[str, float],
            Field(description="{ticker: weight}. Tickers must appear in the data."),
        ],
        data: Annotated[
            dict[str, Any] | None,
            Field(
                default=None,
                description="Inline assets.json payload (covariance + tickers required).",
            ),
        ] = None,
        data_path: Annotated[
            str | None,
            Field(default=None, description="Path to an assets.json on disk."),
        ] = None,
        benchmark_weights: Annotated[
            dict[str, float] | None,
            Field(
                default=None,
                description="{ticker: weight} for benchmark. Enables active share, TE, beta.",
            ),
        ] = None,
        risk_free_rate: Annotated[
            float,
            Field(default=0.0, description="Risk-free rate for Sharpe."),
        ] = 0.0,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, covariance, expected_returns = _read_assets_with_mu(data, data_path)
            result = pyengine.summarize_portfolio(
                weights,
                covariance,
                expected_returns=expected_returns,
                risk_free_rate=risk_free_rate,
                benchmark_weights=benchmark_weights,
                tickers=tickers,
            )
            return render_small_result(
                result, response_format, title="po summarize-portfolio",
                what="po_summarize_portfolio",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_validate_data",
        annotations=READ_ONLY,
        description=(
            "Validate an inline assets payload before paying for an "
            "optimization run. Checks: required keys present (assets, "
            "covariance), ticker uniqueness, dimension consistency between "
            "assets list and covariance matrix, symmetry of Σ, and a "
            "positive-semidefinite check via Cholesky (with a tiny ridge "
            "tolerance). Returns the issues found (empty list = clean)."
        ),
    )
    async def po_validate_data(
        data: Annotated[
            dict[str, Any],
            Field(description="Inline assets.json-shaped payload."),
        ],
        ridge: Annotated[
            float,
            Field(
                default=1e-10,
                description="PSD-check ridge tolerance.",
                ge=0.0,
                le=1e-3,
            ),
        ] = 1e-10,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            issues: list[str] = []
            assets = data.get("assets")
            cov = data.get("covariance")
            if not isinstance(assets, list) or not assets:
                issues.append("`assets` must be a non-empty list.")
            if not isinstance(cov, list) or not cov:
                issues.append("`covariance` must be a non-empty 2D list.")
            tickers: list[str] = []
            if isinstance(assets, list):
                for i, a in enumerate(assets):
                    if not isinstance(a, dict) or "ticker" not in a:
                        issues.append(f"assets[{i}] is missing `ticker`.")
                    else:
                        tickers.append(str(a["ticker"]))
                if len(tickers) != len(set(tickers)):
                    issues.append("duplicate tickers detected in `assets`.")
            if isinstance(cov, list) and tickers:
                n = len(tickers)
                if len(cov) != n:
                    issues.append(
                        f"covariance has {len(cov)} rows but `assets` has {n} entries."
                    )
                for i, row in enumerate(cov):
                    if not isinstance(row, list) or len(row) != n:
                        issues.append(f"covariance row {i} length != {n}.")
                if not issues:
                    issues.extend(_psd_issues(cov, ridge=ridge))
            payload = {
                "n_assets": len(tickers),
                "tickers": tickers,
                "issues": issues,
                "ok": len(issues) == 0,
            }
            return render_small_result(
                payload, response_format, title="po validate-data",
                what="po_validate_data",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_list_results",
        annotations=READ_ONLY,
        description=(
            "Scan $PO_OUTPUT_DIR/results/ and return a summary per "
            "persisted optimization result (label, method, n_assets, top "
            "holdings, key metrics, created_at)."
        ),
    )
    async def po_list_results(
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            entries = registry.list_results()
            payload = {
                "n_results": len(entries),
                "output_dir": str(output_dir()),
                "results": entries,
            }
            return render_small_result(
                payload, response_format, title="po list-results",
                what="po_list_results",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_describe_result",
        annotations=READ_ONLY,
        description=(
            "Load a single persisted result JSON and return its weights, "
            "metrics, and the raw `po` JSON content."
        ),
    )
    async def po_describe_result(
        result_path: Annotated[
            str, Field(description="Absolute path to a result JSON file.")
        ],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            payload = registry.load_result(result_path)
            return render_small_result(
                payload, response_format, title="po describe-result",
                what="po_describe_result",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)


# ---------- internals ----------------------------------------------------


def _read_assets_with_mu(
    data: dict[str, Any] | None, data_path: str | None
) -> tuple[list[str], list[list[float]], dict[str, float] | None]:
    """Resolve and parse an assets.json into ``(tickers, covariance, μ?)``.

    Materializes the inline data into ``$PO_OUTPUT_DIR/tmp/`` for
    downstream-tool reuse.
    """
    if (data is None) == (data_path is None):
        raise POError(
            "Provide exactly one of `data` (inline assets JSON) or `data_path`."
        )
    if data is not None:
        validated = AssetDataInline.model_validate(
            {**{k: v for k, v in data.items() if k != "kind"}, "kind": "inline"}
        )
        materialize_data(validated)
        tickers = [a.ticker for a in validated.assets]
        cov = validated.covariance
        mu = {
            a.ticker: a.expected_return
            for a in validated.assets
            if a.expected_return is not None
        }
    else:
        path = Path(data_path)  # type: ignore[arg-type]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise POError(f"could not read assets file {path}: {exc}") from exc
        assets = payload.get("assets") or []
        tickers = [a.get("ticker", f"asset_{i}") for i, a in enumerate(assets)]
        cov = payload.get("covariance") or []
        mu = {
            a["ticker"]: a["expected_return"]
            for a in assets
            if "ticker" in a and "expected_return" in a
        }
    if not cov:
        raise POError("missing `covariance` in inputs.")
    return tickers, cov, (mu if mu else None)


def _psd_issues(cov: list[list[float]], *, ridge: float) -> list[str]:
    """Run a cheap PSD check on Σ.

    Uses Cholesky on (Σ + ridge·I) if numpy is available; otherwise falls
    back to a symmetry check only.
    """
    issues: list[str] = []
    n = len(cov)
    for i in range(n):
        for j in range(i + 1, n):
            try:
                left = float(cov[i][j])
                right = float(cov[j][i])
            except (TypeError, ValueError, IndexError):
                issues.append(
                    f"Σ has non-numeric or ragged entries at ({i},{j})."
                )
                return issues
            if not math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-9):
                issues.append(
                    f"Σ not symmetric at ({i},{j}): {left} vs {right}."
                )
    if issues:
        return issues
    try:
        import numpy as np
        try:
            sigma = np.asarray(cov, dtype=float)
        except (TypeError, ValueError):
            issues.append("Σ contains non-numeric or ragged entries.")
            return issues
        sigma = sigma + ridge * np.eye(n)
        try:
            np.linalg.cholesky(sigma)
        except np.linalg.LinAlgError:
            eigs = np.linalg.eigvalsh(sigma)
            issues.append(
                f"Σ is not positive semi-definite (min eigenvalue ≈ {float(eigs.min()):.3e})."
            )
    except ImportError:
        pass
    return issues
