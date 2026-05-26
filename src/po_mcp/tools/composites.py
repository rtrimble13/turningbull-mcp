"""CFA-flavored analyst composites.

These tools wire primitive + portopt-supplement calls together into
one-shot workflows that a portfolio manager would naturally request:

- ``po_construct_portfolio`` — "build me a portfolio from these returns".
  Estimates Σ via shrinkage, runs the chosen optimizer, summarizes.
- ``po_compare_methods`` — same data through every requested method,
  ranked comparison table (return, vol, Sharpe, max position, effective N,
  diversification ratio).
- ``po_efficient_frontier_with_targets`` — frontier + highlighted
  target-vol / target-return portfolios.
- ``po_walk_forward_backtest`` — rolling-window estimation + periodic
  rebalance with transaction costs (uses portopt's backtest module).
- ``po_risk_attribution`` — Brinson-Fachler / Brinson-Hood-Beebower.
- ``po_stress_test_portfolio`` — apply scenario shocks to (μ, Σ) and
  report worst-case Sharpe/vol/drawdown.
- ``po_black_litterman_views_workflow`` — convenience wrapper for the
  views→params→`po bl` pipeline.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import pyengine
from ..errors import POError
from ..models import (
    AttributionMode,
    BlackLittermanParams,
    ConstructionMethod,
    Label,
    ResponseFormat,
    Shrinkage,
    materialize_data,
    materialize_params,
)
from ..output import (
    backtests_dir,
    content_hash,
    data_dir,
    frontiers_dir,
    label_or_hash,
    results_dir,
)
from ..runner import get_runner
from ._common import READ_ONLY, render_small_result, wrap_error


# ---------- helpers ------------------------------------------------------


async def _estimate_to_disk(
    returns_csv_path: Path,
    *,
    periods_per_year: int,
    shrinkage: str,
    label: str | None,
) -> tuple[Path, dict[str, Any]]:
    """Run portopt estimation and persist the resulting assets.json.

    Returns ``(path, assets_dict)`` so callers can both pass the path to
    `po` subcommands and reuse the in-memory representation for
    summaries / supplement tools.
    """
    estimated = pyengine.estimate_from_returns(
        returns_csv_path,
        periods_per_year=periods_per_year,
        shrinkage=shrinkage,
    )
    stem = label_or_hash(label, "auto", returns_csv_path.name, shrinkage)
    out_path = data_dir() / f"{stem}.json"
    out_path.write_text(json.dumps(estimated, indent=2, default=str), encoding="utf-8")
    return out_path, estimated


def _params_for_construct(constraints: dict[str, Any] | None) -> Path | None:
    """Wrap an MVO-style constraint dict into a materialized params file."""
    return materialize_params(constraints, kind="mvo") if constraints else None


def _summary_metrics(weights: dict[str, float], assets_dict: dict[str, Any], risk_free_rate: float) -> dict[str, Any]:
    """Compute a uniform metrics block via pyengine.summarize_portfolio."""
    tickers = [a["ticker"] for a in assets_dict.get("assets", [])]
    cov = assets_dict.get("covariance") or []
    mu = {
        a["ticker"]: a["expected_return"]
        for a in assets_dict.get("assets", [])
        if a.get("expected_return") is not None
    }
    summary = pyengine.summarize_portfolio(
        weights,
        cov,
        expected_returns=(mu or None),
        risk_free_rate=risk_free_rate,
        tickers=tickers,
    )
    return summary["metrics"]


# ---------- registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="po_construct_portfolio",
        annotations=READ_ONLY,
        description=(
            "One-shot CFA workflow: estimate (μ, Σ) from a periodic-returns "
            "CSV via shrinkage, then optimize using the chosen method, "
            "then summarize. method ∈ {mvo, max_sharpe, min_variance, "
            "target_vol, target_return, risk_parity, hrp, equal_weight, "
            "inverse_variance, inverse_volatility, max_diversification}. "
            "Pass `target_vol`/`target_return` when method is target_vol/"
            "target_return. Pass `constraints` (MVO-shaped) for bounds, "
            "group caps, turnover penalties, etc."
        ),
    )
    async def po_construct_portfolio(
        returns_csv_path: Annotated[
            str, Field(description="Path to a periodic-returns CSV.")
        ],
        method: Annotated[
            ConstructionMethod,
            Field(description="Construction method."),
        ] = ConstructionMethod.max_sharpe,
        constraints: Annotated[
            dict[str, Any] | None,
            Field(
                default=None,
                description=(
                    "Optional MVO-shaped constraints: lower_bounds, "
                    "upper_bounds, budget, turnover_penalty, "
                    "tracking_error_limit, gross_exposure_limit, groups."
                ),
            ),
        ] = None,
        shrinkage: Annotated[
            Shrinkage,
            Field(description="Covariance shrinkage estimator."),
        ] = Shrinkage.ledoit_wolf,
        risk_free_rate: Annotated[
            float, Field(default=0.0, description="Risk-free rate.")
        ] = 0.0,
        periods_per_year: Annotated[
            int, Field(default=252, description="252 daily, 12 monthly.", ge=1)
        ] = 252,
        target_vol: Annotated[
            float | None,
            Field(default=None, description="Required when method=target_vol."),
        ] = None,
        target_return: Annotated[
            float | None,
            Field(default=None, description="Required when method=target_return."),
        ] = None,
        risk_aversion: Annotated[
            float | None,
            Field(default=None, description="Override risk aversion for mvo/max_sharpe."),
        ] = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            returns_path = Path(returns_csv_path).expanduser()
            if not returns_path.exists():
                raise POError(f"returns CSV not found: {returns_path}")
            data_path, assets_dict = await _estimate_to_disk(
                returns_path,
                periods_per_year=periods_per_year,
                shrinkage=shrinkage.value,
                label=label,
            )
            params_path = _params_for_construct(constraints)
            tickers = [a["ticker"] for a in assets_dict.get("assets", [])]
            covariance = assets_dict.get("covariance") or []
            runner = get_runner()
            method_value = method.value
            weights: dict[str, float]
            extra: dict[str, Any] = {}

            if method_value in (
                "mvo",
                "max_sharpe",
                "min_variance",
                "target_vol",
                "target_return",
            ):
                out = results_dir() / f"{method_value}_{label_or_hash(label, returns_path.stem)}.json"
                runner_method = {
                    "mvo": runner.mvo,
                    "max_sharpe": runner.max_sharpe,
                    "min_variance": runner.min_variance,
                    "target_vol": runner.target_vol,
                    "target_return": runner.target_return,
                }[method_value]
                kw: dict[str, Any] = dict(
                    data_path=data_path,
                    output_path=out,
                    params_path=params_path,
                    risk_free_rate=risk_free_rate,
                    risk_aversion=risk_aversion,
                )
                if method_value == "target_vol":
                    if target_vol is None:
                        raise POError("target_vol method requires `target_vol`.")
                    kw["target"] = target_vol
                if method_value == "target_return":
                    if target_return is None:
                        raise POError("target_return method requires `target_return`.")
                    kw["target"] = target_return
                opt_result = await runner_method(**kw)
                weights = opt_result.weights
                extra["result_json_path"] = str(opt_result.result_json_path)
                extra["solver_diagnostics"] = opt_result.diagnostics
            elif method_value == "risk_parity":
                weights = pyengine.equal_risk_contribution(tickers, covariance)["weights"]
            elif method_value == "hrp":
                weights = pyengine.hierarchical_risk_parity(tickers, covariance)["weights"]
            elif method_value == "equal_weight":
                weights = pyengine.equal_weight(tickers)["weights"]
            elif method_value == "inverse_variance":
                weights = pyengine.inverse_variance(tickers, covariance)["weights"]
            elif method_value == "inverse_volatility":
                weights = pyengine.inverse_volatility(tickers, covariance)["weights"]
            elif method_value == "max_diversification":
                weights = pyengine.max_diversification(tickers, covariance)["weights"]
            else:
                raise POError(f"unsupported method: {method_value!r}")

            metrics = _summary_metrics(weights, assets_dict, risk_free_rate)
            payload = {
                "method": method_value,
                "shrinkage": shrinkage.value,
                "periods_per_year": periods_per_year,
                "weights": weights,
                "metrics": metrics,
                "tickers": tickers,
                "artifacts": {
                    "returns_csv": str(returns_path),
                    "assets_json": str(data_path),
                    "params_json": str(params_path) if params_path else None,
                    **extra,
                },
            }
            return render_small_result(
                payload, response_format,
                title=f"po construct ({method_value})",
                what="po_construct_portfolio",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_compare_methods",
        annotations=READ_ONLY,
        description=(
            "Estimate once from a returns CSV, run multiple construction "
            "methods on the same Σ/μ, and return a ranked comparison "
            "table: expected return, volatility, Sharpe, max position, "
            "effective N, diversification ratio, turnover-vs-equal-weight. "
            "Useful for sanity checks ('does MVO over-concentrate vs HRP?')."
        ),
    )
    async def po_compare_methods(
        returns_csv_path: Annotated[
            str, Field(description="Path to a periodic-returns CSV.")
        ],
        methods: Annotated[
            list[ConstructionMethod] | None,
            Field(
                default=None,
                description=(
                    "Methods to compare. Default: "
                    "[mvo, max_sharpe, min_variance, risk_parity, hrp, "
                    "equal_weight, inverse_variance, max_diversification]."
                ),
            ),
        ] = None,
        constraints: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Shared MVO-style constraints applied to MVO methods."),
        ] = None,
        shrinkage: Annotated[
            Shrinkage,
            Field(description="Covariance shrinkage."),
        ] = Shrinkage.ledoit_wolf,
        risk_free_rate: Annotated[
            float, Field(default=0.0, description="Risk-free rate.")
        ] = 0.0,
        periods_per_year: Annotated[
            int, Field(default=252, description="252 daily, 12 monthly.", ge=1)
        ] = 252,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            returns_path = Path(returns_csv_path).expanduser()
            if not returns_path.exists():
                raise POError(f"returns CSV not found: {returns_path}")
            chosen = methods or [
                ConstructionMethod.mvo,
                ConstructionMethod.max_sharpe,
                ConstructionMethod.min_variance,
                ConstructionMethod.risk_parity,
                ConstructionMethod.hrp,
                ConstructionMethod.equal_weight,
                ConstructionMethod.inverse_variance,
                ConstructionMethod.max_diversification,
            ]
            data_path, assets_dict = await _estimate_to_disk(
                returns_path,
                periods_per_year=periods_per_year,
                shrinkage=shrinkage.value,
                label=label,
            )
            params_path = _params_for_construct(constraints)
            tickers = [a["ticker"] for a in assets_dict.get("assets", [])]
            covariance = assets_dict.get("covariance") or []
            runner = get_runner()
            n = len(tickers)
            equal_w = {t: 1.0 / n for t in tickers} if n else {}

            tasks: list[tuple[str, Any]] = []
            sync_results: dict[str, dict[str, float]] = {}
            for m in chosen:
                mv = m.value
                if mv in ("mvo", "max_sharpe", "min_variance"):
                    out = results_dir() / f"{mv}_{label_or_hash(label, returns_path.stem)}.json"
                    runner_method = {
                        "mvo": runner.mvo,
                        "max_sharpe": runner.max_sharpe,
                        "min_variance": runner.min_variance,
                    }[mv]
                    tasks.append((mv, runner_method(
                        data_path=data_path,
                        output_path=out,
                        params_path=params_path,
                        risk_free_rate=risk_free_rate,
                    )))
                elif mv == "risk_parity":
                    sync_results[mv] = pyengine.equal_risk_contribution(tickers, covariance)["weights"]
                elif mv == "hrp":
                    sync_results[mv] = pyengine.hierarchical_risk_parity(tickers, covariance)["weights"]
                elif mv == "equal_weight":
                    sync_results[mv] = pyengine.equal_weight(tickers)["weights"]
                elif mv == "inverse_variance":
                    sync_results[mv] = pyengine.inverse_variance(tickers, covariance)["weights"]
                elif mv == "inverse_volatility":
                    sync_results[mv] = pyengine.inverse_volatility(tickers, covariance)["weights"]
                elif mv == "max_diversification":
                    sync_results[mv] = pyengine.max_diversification(tickers, covariance)["weights"]
                # target_vol/target_return omitted from compare (need extra param)

            async_results: dict[str, dict[str, float]] = {}
            if tasks:
                names, coros = zip(*tasks)
                outcomes = await asyncio.gather(*coros)
                for name, outcome in zip(names, outcomes):
                    async_results[name] = outcome.weights

            all_weights = {**async_results, **sync_results}
            rows: list[dict[str, Any]] = []
            for mv, w in all_weights.items():
                metrics = _summary_metrics(w, assets_dict, risk_free_rate)
                turnover_vs_ew = (
                    sum(abs(w.get(t, 0.0) - equal_w.get(t, 0.0)) for t in tickers) / 2.0
                    if tickers
                    else 0.0
                )
                rows.append(
                    {
                        "method": mv,
                        "expected_return": metrics.get("expected_return"),
                        "volatility": metrics.get("volatility"),
                        "sharpe_ratio": metrics.get("sharpe_ratio"),
                        "max_position": metrics.get("max_position"),
                        "effective_n": metrics.get("effective_n"),
                        "diversification_ratio": metrics.get("diversification_ratio"),
                        "turnover_vs_equal_weight": turnover_vs_ew,
                    }
                )
            rows.sort(
                key=lambda r: (r.get("sharpe_ratio") if r.get("sharpe_ratio") is not None else float("-inf")),
                reverse=True,
            )
            payload = {
                "shrinkage": shrinkage.value,
                "n_assets": n,
                "tickers": tickers,
                "rows": rows,
                "artifacts": {
                    "returns_csv": str(returns_path),
                    "assets_json": str(data_path),
                    "params_json": str(params_path) if params_path else None,
                },
            }
            return render_small_result(
                payload, response_format,
                title="po compare-methods",
                what="po_compare_methods",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_efficient_frontier_with_targets",
        annotations=READ_ONLY,
        description=(
            "Compute the MVO efficient frontier and additionally pin "
            "specific target-volatility and/or target-return portfolios "
            "(one tool call instead of three). Returns the frontier CSV "
            "path, summary points (min-vol, max-sharpe, max-return), and "
            "a list of `targets` with each pinned portfolio's weights + "
            "metrics."
        ),
    )
    async def po_efficient_frontier_with_targets(
        target_vols: Annotated[
            list[float] | None,
            Field(default=None, description="Annualized target-vol pins, e.g. [0.10, 0.15, 0.20]."),
        ] = None,
        target_returns: Annotated[
            list[float] | None,
            Field(default=None, description="Annualized target-return pins."),
        ] = None,
        data: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Inline assets payload."),
        ] = None,
        data_path: Annotated[
            str | None,
            Field(default=None, description="Path to assets.json."),
        ] = None,
        params: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="MVO constraints / params."),
        ] = None,
        risk_free_rate: Annotated[
            float | None,
            Field(default=None, description="Risk-free rate."),
        ] = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            from . import primitives as _prim
            data_p = _prim._resolve_data_input(data, data_path)
            params_p = _prim._resolve_params_input(params, kind="mvo")
            runner = get_runner()
            frontier_out = frontiers_dir() / (
                f"frontier_{label_or_hash(label, str(data_p), str(params_p or ''))}.csv"
            )
            front = await runner.frontier(
                data_path=data_p,
                output_path=frontier_out,
                params_path=params_p,
                risk_free_rate=risk_free_rate,
            )
            targets: list[dict[str, Any]] = []
            scheduled: list[tuple[str, float, Any]] = []
            for tv in target_vols or []:
                out = results_dir() / f"target_vol_{label_or_hash(label, str(data_p), f'tv{tv}')}.json"
                scheduled.append((
                    "target_vol",
                    tv,
                    runner.target_vol(
                        data_path=data_p,
                        target=tv,
                        output_path=out,
                        params_path=params_p,
                        risk_free_rate=risk_free_rate,
                    ),
                ))
            for tr in target_returns or []:
                out = results_dir() / f"target_return_{label_or_hash(label, str(data_p), f'tr{tr}')}.json"
                scheduled.append((
                    "target_return",
                    tr,
                    runner.target_return(
                        data_path=data_p,
                        target=tr,
                        output_path=out,
                        params_path=params_p,
                        risk_free_rate=risk_free_rate,
                    ),
                ))
            if scheduled:
                outcomes = await asyncio.gather(*[c for _, _, c in scheduled])
                for (kind, target_val, _), result in zip(scheduled, outcomes):
                    targets.append(
                        {
                            "kind": kind,
                            "target": target_val,
                            "weights": result.weights,
                            "metrics": result.metrics,
                            "result_json_path": str(result.result_json_path),
                        }
                    )
            payload = {
                "method": "efficient_frontier_with_targets",
                "frontier_csv_path": str(front.frontier_csv_path),
                "summary": front.summary,
                "n_points": len(front.rows),
                "rows_head": front.rows[:5],
                "rows_tail": front.rows[-5:] if len(front.rows) > 5 else [],
                "targets": targets,
                "artifacts": {
                    "data": str(data_p),
                    "params": str(params_p) if params_p else None,
                    "frontier_csv": str(front.frontier_csv_path),
                },
            }
            return render_small_result(
                payload, response_format,
                title="po frontier + targets",
                what="po_efficient_frontier_with_targets",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_walk_forward_backtest",
        annotations=READ_ONLY,
        description=(
            "Rolling-window estimation + periodic rebalance backtest via "
            "portopt.backtest.walk_forward. Estimates Σ from each `window` "
            "of periods, rebalances every `step` periods using `strategy`, "
            "and applies a per-rebalance L1 transaction cost. Returns "
            "equity curve, CAGR, Sharpe, Sortino, max drawdown, total "
            "turnover/transaction cost, and (if benchmark provided) "
            "tracking error and information ratio. Requires `portopt`."
        ),
    )
    async def po_walk_forward_backtest(
        returns_csv_path: Annotated[
            str, Field(description="Periodic returns CSV.")
        ],
        strategy: Annotated[
            Literal[
                "mvo",
                "min_variance",
                "max_sharpe",
                "risk_parity",
                "hrp",
                "equal_weight",
                "inverse_variance",
                "inverse_volatility",
            ],
            Field(description="Per-window rebalance strategy."),
        ] = "max_sharpe",
        window: Annotated[
            int, Field(description="Estimation window length (periods).", ge=20)
        ] = 126,
        step: Annotated[
            int, Field(description="Rebalance interval (periods).", ge=1)
        ] = 21,
        transaction_cost: Annotated[
            float,
            Field(description="L1 transaction cost per unit turnover.", ge=0.0),
        ] = 0.0005,
        periods_per_year: Annotated[
            int, Field(description="252 daily, 12 monthly.", ge=1)
        ] = 252,
        shrinkage: Annotated[
            Shrinkage, Field(description="Covariance shrinkage.")
        ] = Shrinkage.ledoit_wolf,
        risk_aversion: Annotated[
            float, Field(description="Used by mvo strategy.", gt=0.0)
        ] = 2.5,
        benchmark_returns_csv_path: Annotated[
            str | None,
            Field(default=None, description="Optional benchmark returns CSV for TE / IR."),
        ] = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            path = Path(returns_csv_path).expanduser()
            if not path.exists():
                raise POError(f"returns CSV not found: {path}")
            bench_path = (
                Path(benchmark_returns_csv_path).expanduser()
                if benchmark_returns_csv_path
                else None
            )
            if bench_path and not bench_path.exists():
                raise POError(f"benchmark CSV not found: {bench_path}")
            result = pyengine.walk_forward_backtest(
                path,
                strategy=strategy,
                window=window,
                step=step,
                transaction_cost=transaction_cost,
                periods_per_year=periods_per_year,
                shrinkage=shrinkage.value,
                risk_aversion=risk_aversion,
                benchmark_returns_csv_path=bench_path,
            )
            stem = label_or_hash(label, "backtest", path.stem, strategy)
            out_path = backtests_dir() / f"{stem}.json"
            out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            payload = {
                "strategy": strategy,
                "window": window,
                "step": step,
                "transaction_cost": transaction_cost,
                "summary": result.get("summary", {}),
                "n_periods": result.get("summary", {}).get("n_periods"),
                "n_rebalances": result.get("n_rebalances"),
                "equity_curve_head": result.get("equity_curve", [])[:5],
                "equity_curve_tail": result.get("equity_curve", [])[-5:],
                "artifacts": {
                    "backtest_json": str(out_path),
                    "returns_csv": str(path),
                    "benchmark_csv": str(bench_path) if bench_path else None,
                },
            }
            return render_small_result(
                payload, response_format,
                title=f"po walk-forward ({strategy})",
                what="po_walk_forward_backtest",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_risk_attribution",
        annotations=READ_ONLY,
        description=(
            "Brinson decomposition of active return between a portfolio "
            "and a benchmark, grouped (e.g. by sector). Mode "
            "'brinson_fachler' returns allocation + selection; "
            "'brinson_hood_beebower' additionally returns interaction. "
            "All inputs are {group_name: value} dicts. Requires `portopt`."
        ),
    )
    async def po_risk_attribution(
        portfolio_group_weights: Annotated[
            dict[str, float],
            Field(description="{group: weight} for the portfolio."),
        ],
        benchmark_group_weights: Annotated[
            dict[str, float],
            Field(description="{group: weight} for the benchmark."),
        ],
        portfolio_group_returns: Annotated[
            dict[str, float],
            Field(description="{group: return} for the portfolio."),
        ],
        benchmark_group_returns: Annotated[
            dict[str, float],
            Field(description="{group: return} for the benchmark."),
        ],
        mode: Annotated[
            AttributionMode,
            Field(description="brinson_fachler (default) or brinson_hood_beebower."),
        ] = AttributionMode.brinson_fachler,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            payload = pyengine.brinson_attribution(
                group_weights_p=portfolio_group_weights,
                group_weights_b=benchmark_group_weights,
                group_returns_p=portfolio_group_returns,
                group_returns_b=benchmark_group_returns,
                mode=mode.value,
            )
            return render_small_result(
                payload, response_format,
                title=f"po attribution ({mode.value})",
                what="po_risk_attribution",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_stress_test_portfolio",
        annotations=READ_ONLY,
        description=(
            "Apply scenario shocks to (μ, Σ) and recompute portfolio "
            "metrics under each scenario. A scenario is "
            "{name, expected_return_multiplier?, expected_return_shift?, "
            "covariance_multiplier?, sector_shock? {sector: shift}, "
            "ticker_shock? {ticker: shift}}. Reports per-scenario "
            "expected return, vol, Sharpe, max drawdown proxy, plus the "
            "worst-case row."
        ),
    )
    async def po_stress_test_portfolio(
        weights: Annotated[
            dict[str, float],
            Field(description="{ticker: weight} of the portfolio under test."),
        ],
        shock_scenarios: Annotated[
            list[dict[str, Any]],
            Field(description="List of scenario specs. See description."),
        ],
        data: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Inline assets.json payload."),
        ] = None,
        data_path: Annotated[
            str | None,
            Field(default=None, description="Path to assets.json."),
        ] = None,
        risk_free_rate: Annotated[
            float, Field(default=0.0, description="Risk-free rate for Sharpe.")
        ] = 0.0,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            from .data import _read_assets_with_mu  # local import to avoid cycle

            tickers, cov, mu = _read_assets_with_mu(data, data_path)
            rows: list[dict[str, Any]] = []
            # Sector lookup for sector_shock support
            sector_of: dict[str, str | None] = {}
            if data is not None:
                for a in data.get("assets", []):
                    sector_of[a.get("ticker", "")] = a.get("sector")
            elif data_path is not None:
                try:
                    payload_d = json.loads(Path(data_path).read_text(encoding="utf-8"))
                    for a in payload_d.get("assets", []):
                        sector_of[a.get("ticker", "")] = a.get("sector")
                except (OSError, json.JSONDecodeError):
                    pass

            for sc in shock_scenarios:
                name = sc.get("name", "unnamed")
                mu_shocked = dict(mu) if mu else {}
                mul = sc.get("expected_return_multiplier")
                shift = sc.get("expected_return_shift")
                if mul is not None:
                    mu_shocked = {t: v * float(mul) for t, v in mu_shocked.items()}
                if shift is not None:
                    mu_shocked = {t: v + float(shift) for t, v in mu_shocked.items()}
                if isinstance(sc.get("ticker_shock"), dict):
                    for t, delta in sc["ticker_shock"].items():
                        mu_shocked[t] = mu_shocked.get(t, 0.0) + float(delta)
                if isinstance(sc.get("sector_shock"), dict):
                    for sector, delta in sc["sector_shock"].items():
                        for tk, sec in sector_of.items():
                            if sec == sector:
                                mu_shocked[tk] = mu_shocked.get(tk, 0.0) + float(delta)
                cov_mul = float(sc.get("covariance_multiplier", 1.0))
                shocked_cov = [[v * cov_mul for v in row] for row in cov]
                summary = pyengine.summarize_portfolio(
                    weights,
                    shocked_cov,
                    expected_returns=(mu_shocked or None),
                    risk_free_rate=risk_free_rate,
                    tickers=tickers,
                )
                rows.append(
                    {
                        "scenario": name,
                        "metrics": summary["metrics"],
                    }
                )
            worst = min(
                rows,
                key=lambda r: (
                    r["metrics"].get("sharpe_ratio")
                    if r["metrics"].get("sharpe_ratio") is not None
                    else float("inf")
                ),
                default=None,
            )
            payload = {
                "n_scenarios": len(rows),
                "scenarios": rows,
                "worst_case_by_sharpe": worst,
            }
            return render_small_result(
                payload, response_format,
                title="po stress-test",
                what="po_stress_test_portfolio",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_black_litterman_views_workflow",
        annotations=READ_ONLY,
        description=(
            "Convenience wrapper: build a BL params payload from a list of "
            "views and dispatch `po bl`. Views may use ticker-keyed "
            "pick_vectors. Returns the same shape as po_black_litterman."
        ),
    )
    async def po_black_litterman_views_workflow(
        views: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "List of {pick_vector: {ticker: weight} | [floats], "
                    "expected_return, confidence?, description?} views."
                ),
            ),
        ],
        data: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Inline assets payload."),
        ] = None,
        data_path: Annotated[
            str | None,
            Field(default=None, description="Path to assets.json."),
        ] = None,
        tau: Annotated[
            float, Field(default=0.05, description="BL tau (default 0.05).", gt=0.0)
        ] = 0.05,
        risk_aversion: Annotated[
            float, Field(default=2.5, description="BL risk aversion (default 2.5).", gt=0.0)
        ] = 2.5,
        confidence_mode: Annotated[
            Literal["idzorek", "omega-direct"],
            Field(default="idzorek", description="Confidence mode."),
        ] = "idzorek",
        show_model: Annotated[
            bool,
            Field(default=False, description="Print BL diagnostics."),
        ] = False,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            from . import primitives as _prim

            data_p = _prim._resolve_data_input(data, data_path)
            bl_params = BlackLittermanParams.model_validate(
                {
                    "tau": tau,
                    "risk_aversion": risk_aversion,
                    "confidence_mode": confidence_mode,
                    "views": views,
                }
            )
            params_p = materialize_params(bl_params, kind="bl")
            if params_p is None:
                raise POError("BL workflow requires at least one view.")
            out = results_dir() / f"bl_{label_or_hash(label, str(data_p), str(params_p))}.json"
            result = await get_runner().bl(
                data_path=data_p,
                params_path=params_p,
                output_path=out,
                show_model=show_model,
            )
            payload = {
                "method": "bl_workflow",
                "weights": result.weights,
                "metrics": result.metrics,
                "diagnostics": result.diagnostics,
                "result_json_path": str(result.result_json_path),
                "n_views": len(views),
                "tau": tau,
                "risk_aversion": risk_aversion,
                "confidence_mode": confidence_mode,
                "argv": result.argv,
                "artifacts": {
                    "data": str(data_p),
                    "params": str(params_p),
                    "result": str(result.result_json_path),
                },
            }
            return render_small_result(
                payload, response_format,
                title="po bl-views-workflow",
                what="po_black_litterman_views_workflow",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
