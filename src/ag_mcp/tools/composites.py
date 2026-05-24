"""Analyst-grade composite workflows.

Each tool here strings several primitives together so a single MCP call
produces a self-contained answer to a real quant question:

- ``ag_volatility_snapshot`` — "How volatile is X, is the model adequate,
  and what's the conditional-volatility forecast?"
- ``ag_var_snapshot`` — "What's the h-day VaR at confidence c?"
- ``ag_forecast_distribution`` — quantile fan from a Monte Carlo.
- ``ag_compare_volatility`` — ranked panel of volatility clustering.
- ``ag_macro_volatility_snapshot`` — same shape for BLS/BEA macro series.
- ``ag_stress_test`` — heavy-tail / Gaussian comparison via large MC.

Diagnostic gating is first-class in every response: every composite that
produces a forecast or VaR carries a top-level ``model_adequate: bool``
plus ``model_adequate_reasons: [...]`` so the caller never has to read
free text to know whether to trust the number.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Annotated, Any, Literal

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..errors import AGError
from ..models import (
    Frequency,
    InnovationDist,
    Label,
    ResponseFormat,
    ReturnType,
    SelectionCriterion,
    annualization_factor_for,
)
from ..output import (
    forecasts_dir,
    models_dir,
    safe_filename,
    simulations_dir,
)
from ..preprocessing import ReturnsMetadata
from ..registry import load_model
from ..runner import get_runner
from ._common import READ_ONLY, render_small_result, wrap_error
from .data import _load_series_impl
from .primitives import (
    _diagnostics_filename,
    _fit_summary,
    _forecast_filename,
    _model_adequate,
    _model_adequate_reasons,
    _spec_label,
    _summarize_forecast_rows,
)


# ---------- low-level orchestration --------------------------------------


async def _fit_or_select(
    *,
    data_path: Path,
    out_path: Path,
    auto_select: bool,
    criterion: SelectionCriterion,
    arima: tuple[int, int, int],
    garch: tuple[int, int],
    innovation: InnovationDist,
    t_df: float | None,
) -> dict[str, Any]:
    """Run select-then-fall-back-to-fit, returning the parsed model block."""
    runner = get_runner()
    if auto_select:
        sel = await runner.select(
            data_path=data_path,
            output_path=out_path,
            criterion=criterion.value,
        )
        return {
            "model_path": str(sel.model_path),
            "parsed": sel.parsed,
            "raw_stdout": sel.raw_stdout,
        }
    fit = await runner.fit(
        data_path=data_path,
        arima=arima,
        garch=garch,
        innovation=innovation.value,
        t_df=t_df,
        output_path=out_path,
    )
    return {
        "model_path": str(fit.model_path),
        "parsed": fit.parsed,
        "raw_stdout": fit.raw_stdout,
    }


def _period_default_dates(years_back: float | int) -> tuple[str, str]:
    today = date.today()
    days = int(round(float(years_back) * 365))
    return ((today - timedelta(days=days)).isoformat(), today.isoformat())


def _years_back_from_period(period: str) -> float:
    """Parse a friendly period spec like '5y', '3y', '6mo', '30d'."""
    s = period.strip().lower()
    if s.endswith("y"):
        return float(s[:-1] or 1)
    if s.endswith("mo"):
        return float(s[:-2] or 1) / 12.0
    if s.endswith("m"):
        return float(s[:-1] or 1) / 12.0
    if s.endswith("d"):
        return float(s[:-1] or 1) / 365.0
    raise AGError(
        f"period {period!r} must end with y/mo/m/d, e.g. '5y' or '6mo'."
    )


def _normal_quantile(p: float) -> float:
    return NormalDist().inv_cdf(p)


def _build_distribution_recommendation(
    parsed: dict[str, Any], *, symbol_or_series: str, data_path: str
) -> dict[str, Any]:
    """Render the Student-t recommendation block (or None) for the response.

    Surfaces the suggested df and the exact ``ag_fit(...)`` tool call that
    would refit the model with the recommendation — never auto-refits; the
    caller decides.
    """
    if not parsed.get("student_t_recommended"):
        return {
            "fitted_with": parsed.get("distribution_used") or "gaussian",
            "student_t_recommended": False,
        }
    df = parsed.get("student_t_df_suggested")
    df_arg = f", t_df={df:.2f}" if isinstance(df, (int, float)) else ""
    return {
        "fitted_with": parsed.get("distribution_used") or "gaussian",
        "student_t_recommended": True,
        "suggested_df": df,
        "rerun_command": (
            f"ag_fit(data_path='{data_path}', "
            f"arima={list(parsed.get('arima') or [])}, "
            f"garch={list(parsed.get('garch') or [])}, "
            f"innovation='student_t'{df_arg}, "
            f"label='{symbol_or_series}_student_t')"
        ),
    }


# ---------- registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="ag_volatility_snapshot",
        annotations=READ_ONLY,
        description=(
            "End-to-end volatility one-pager for a single ticker. Pipeline: "
            "FMP historical prices -> log returns -> ag_select (BIC) -> "
            "ag_diagnostics -> ag_forecast(horizon=22 trading days). "
            "Returns the fitted spec, params, persistence (with near-unit-"
            "root flag), unconditional variance (when defined), the three "
            "diagnostic test p-values, model_adequate: bool, the Student-t "
            "recommendation (with the exact rerun command), current "
            "conditional vol (per-period + annualized), the 1/5/22-day "
            "horizon forecasts (per-period + annualized), and the paths to "
            "every artifact. Use this for 'how volatile is X right now?' "
            "and 'is the model trustworthy?' questions."
        ),
    )
    async def ag_volatility_snapshot(
        symbol: Annotated[str, Field(description="FMP ticker, e.g. NVDA or SPY.")],
        period: Annotated[
            str,
            Field(description="History window: e.g. '5y' (default), '10y', '3y'."),
        ] = "5y",
        auto_select: Annotated[
            bool,
            Field(description="Run ag_select on a small grid (default true)."),
        ] = True,
        criterion: Annotated[
            SelectionCriterion,
            Field(description="Selection criterion when auto_select=true."),
        ] = SelectionCriterion.BIC,
        innovation: Annotated[
            InnovationDist,
            Field(description="Used only when auto_select=false."),
        ] = InnovationDist.gaussian,
        forecast_horizon: Annotated[
            int,
            Field(description="Forecast horizon in trading days (default 22 ≈ 1 month).", ge=1, le=2000),
        ] = 22,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            years_back = _years_back_from_period(period)
            from_d, to_d = _period_default_dates(years_back)
            meta = await _load_series_impl(
                source="fmp_prices",
                identifier=symbol,
                from_date=from_d,
                to_date=to_d,
                return_type=ReturnType.log,
                price_column="adjClose",
            )
            payload = await _volatility_snapshot_impl(
                identifier=symbol,
                meta=meta,
                auto_select=auto_select,
                criterion=criterion,
                innovation=innovation,
                forecast_horizon=forecast_horizon,
            )
            return render_small_result(
                payload,
                response_format,
                title=f"Volatility snapshot: {symbol}",
                what="ag_volatility_snapshot",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_var_snapshot",
        annotations=READ_ONLY,
        description=(
            "Multi-day VaR / Expected Shortfall via Monte Carlo. Pipeline: "
            "FMP prices -> log returns -> ag_select -> ag_simulate(paths, "
            "horizon_days) -> empirical quantile of cumulative returns at "
            "horizon. Also reports parametric Gaussian VaR for context "
            "and the empirical/parametric ratio (fat-tail uplift). When "
            "the fitted model recommends Student-t but was fit Gaussian, "
            "a warning explicitly says tail risk is likely understated. "
            "portfolio_value scales VaR/ES into dollar terms (default 1.0 "
            "for percent-of-NAV)."
        ),
    )
    async def ag_var_snapshot(
        symbol: Annotated[str, Field(description="FMP ticker.")],
        horizon_days: Annotated[int, Field(description="VaR horizon in trading days.", ge=1, le=500)] = 10,
        confidence: Annotated[
            float, Field(description="VaR confidence (e.g. 0.95, 0.99).", gt=0.5, lt=1.0)
        ] = 0.95,
        paths: Annotated[int, Field(description="MC paths (default 2000).", ge=100, le=200000)] = 2000,
        period: Annotated[str, Field(description="Training window (default '5y').")] = "5y",
        portfolio_value: Annotated[
            float,
            Field(description="Notional NAV (defaults to 1.0 = report in %)."),
        ] = 1.0,
        criterion: Annotated[
            SelectionCriterion,
            Field(description="Selection criterion (default BIC)."),
        ] = SelectionCriterion.BIC,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            years_back = _years_back_from_period(period)
            from_d, to_d = _period_default_dates(years_back)
            meta = await _load_series_impl(
                source="fmp_prices",
                identifier=symbol,
                from_date=from_d,
                to_date=to_d,
                return_type=ReturnType.log,
                price_column="adjClose",
            )
            payload = await _var_snapshot_impl(
                identifier=symbol,
                meta=meta,
                horizon_days=horizon_days,
                confidence=confidence,
                paths=paths,
                portfolio_value=portfolio_value,
                criterion=criterion,
            )
            return render_small_result(
                payload,
                response_format,
                title=f"VaR snapshot: {symbol} ({horizon_days}d, {confidence:.0%})",
                what="ag_var_snapshot",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_forecast_distribution",
        annotations=READ_ONLY,
        description=(
            "Quantile fan chart from a Monte Carlo of `paths` simulations. "
            "Accepts EITHER a saved model JSON path OR a symbol (in which "
            "case the same FMP-prices->log-returns->ag_select pipeline as "
            "ag_volatility_snapshot runs first). Returns the quantile table "
            "(5/10/25/50/75/90/95) at each horizon step, the full simulation "
            "CSV path, the model spec, and model_adequate."
        ),
    )
    async def ag_forecast_distribution(
        symbol_or_model_path: Annotated[
            str,
            Field(description="A FMP ticker OR an absolute path to a saved model JSON."),
        ],
        horizon: Annotated[int, Field(description="Steps per simulated path.", ge=1, le=1000)] = 22,
        paths: Annotated[int, Field(description="MC paths.", ge=100, le=200000)] = 1000,
        period: Annotated[
            str,
            Field(description="Training window if a symbol is passed (default '5y')."),
        ] = "5y",
        criterion: Annotated[
            SelectionCriterion,
            Field(description="Selection criterion when fitting from a symbol."),
        ] = SelectionCriterion.BIC,
        seed: Annotated[int, Field(description="RNG seed.")] = 42,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            payload = await _forecast_distribution_impl(
                token=symbol_or_model_path,
                horizon=horizon,
                paths=paths,
                period=period,
                criterion=criterion,
                seed=seed,
            )
            return render_small_result(
                payload,
                response_format,
                title=f"Forecast distribution: {symbol_or_model_path}",
                what="ag_forecast_distribution",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_compare_volatility",
        annotations=READ_ONLY,
        description=(
            "Side-by-side volatility-clustering table for a list of tickers. "
            "For each symbol: pull FMP prices, derive log returns, fit a "
            "parsimonious model (default ARIMA(1,0,1)-GARCH(1,1) unless "
            "criterion is set), and report n_obs, annualized realized vol, "
            "annualized unconditional vol (when persistence < 1), "
            "persistence, distribution_used, student_t_recommended, input "
            "excess kurtosis, and model_adequate. Sorted by persistence "
            "descending (highest = most volatility clustering)."
        ),
    )
    async def ag_compare_volatility(
        symbols: Annotated[
            list[str],
            Field(description="List of FMP tickers, e.g. ['META','AAPL','AMZN']."),
        ],
        period: Annotated[str, Field(description="Training window (default '3y').")] = "3y",
        criterion: Annotated[
            SelectionCriterion | Literal["fixed"],
            Field(
                description=(
                    "BIC/AIC/AICc/CV run ag_select; 'fixed' (default) just "
                    "fits ARIMA(1,0,1)-GARCH(1,1) for speed."
                ),
            ),
        ] = "fixed",
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            payload = await _compare_volatility_impl(
                symbols=symbols,
                period=period,
                criterion=criterion,
            )
            return render_small_result(
                payload,
                response_format,
                title=f"Volatility comparison: {','.join(symbols)}",
                what="ag_compare_volatility",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_macro_volatility_snapshot",
        annotations=READ_ONLY,
        description=(
            "Same shape as ag_volatility_snapshot but for BLS/BEA macro "
            "series. Defaults return_type='none' because BLS YoY series "
            "and BEA growth rates are already stationary. Pass "
            "return_type='log' for index-level series (e.g. CPI level). "
            "Cadence and annualization factor are inferred from observed "
            "spacing (monthly series get factor=12, quarterly=4)."
        ),
    )
    async def ag_macro_volatility_snapshot(
        series_id: Annotated[str, Field(description="BLS series_id or BEA label.")],
        source: Annotated[
            Literal["bls", "bea"],
            Field(description="'bls' or 'bea' (controls which API is queried)."),
        ] = "bls",
        lookback_years: Annotated[
            int, Field(description="Years of history to pull (default 20).", ge=1, le=80)
        ] = 20,
        return_type: Annotated[
            ReturnType,
            Field(description="Default 'none' (macro series are already stationary)."),
        ] = ReturnType.none,
        forecast_horizon: Annotated[
            int, Field(description="Forecast horizon in periods (default 12).", ge=1, le=120)
        ] = 12,
        extras: Annotated[
            dict[str, Any] | None,
            Field(description="Required for source='bea': dataset/TableName/etc."),
        ] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            from_d, to_d = _period_default_dates(lookback_years)
            full_source = "bls_series" if source == "bls" else "bea_series"
            meta = await _load_series_impl(
                source=full_source,  # type: ignore[arg-type]
                identifier=series_id,
                from_date=from_d,
                to_date=to_d,
                return_type=return_type,
                extras=extras,
            )
            payload = await _volatility_snapshot_impl(
                identifier=series_id,
                meta=meta,
                auto_select=True,
                criterion=SelectionCriterion.BIC,
                innovation=InnovationDist.gaussian,
                forecast_horizon=forecast_horizon,
            )
            payload["macro_source"] = source
            return render_small_result(
                payload,
                response_format,
                title=f"Macro volatility snapshot: {series_id}",
                what="ag_macro_volatility_snapshot",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_stress_test",
        annotations=READ_ONLY,
        description=(
            "Heavy-tail vs Gaussian stress test for a single symbol via "
            "large MC simulation. scenario picks the innovation: "
            "'gaussian', 'student_t_df5', 'student_t_df3'. Returns the "
            "return distribution at horizon (1/5/10/50/90/95/99 percentiles), "
            "probability of loss > 5/10/20%, the worst/best simulated path, "
            "and the saved simulation CSV. Run this across all three "
            "scenarios to see how much your tail risk depends on the "
            "innovation distribution assumption."
        ),
    )
    async def ag_stress_test(
        symbol: Annotated[str, Field(description="FMP ticker.")],
        scenario: Annotated[
            Literal["gaussian", "student_t_df5", "student_t_df3"],
            Field(description="Innovation scenario."),
        ] = "student_t_df3",
        horizon_days: Annotated[int, Field(description="Steps per path.", ge=1, le=500)] = 22,
        paths: Annotated[int, Field(description="MC paths.", ge=500, le=200000)] = 5000,
        period: Annotated[str, Field(description="Training window (default '5y').")] = "5y",
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            years_back = _years_back_from_period(period)
            from_d, to_d = _period_default_dates(years_back)
            meta = await _load_series_impl(
                source="fmp_prices",
                identifier=symbol,
                from_date=from_d,
                to_date=to_d,
                return_type=ReturnType.log,
                price_column="adjClose",
            )
            payload = await _stress_test_impl(
                identifier=symbol,
                meta=meta,
                scenario=scenario,
                horizon_days=horizon_days,
                paths=paths,
            )
            return render_small_result(
                payload,
                response_format,
                title=f"Stress test: {symbol} ({scenario})",
                what="ag_stress_test",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)


# ---------- composite implementations (callable from tests too) ----------


async def _volatility_snapshot_impl(
    *,
    identifier: str,
    meta: ReturnsMetadata,
    auto_select: bool,
    criterion: SelectionCriterion,
    innovation: InnovationDist,
    forecast_horizon: int,
) -> dict[str, Any]:
    """Shared core for ag_volatility_snapshot and ag_macro_volatility_snapshot."""
    runner = get_runner()
    data_path = Path(meta.returns_csv_path)
    stem = safe_filename(identifier) or "series"
    out_model = models_dir() / f"{stem}_snapshot_{criterion.value}.json"
    model_block = await _fit_or_select(
        data_path=data_path,
        out_path=out_model,
        auto_select=auto_select,
        criterion=criterion,
        arima=(1, 0, 1),
        garch=(1, 1),
        innovation=innovation,
        t_df=None,
    )
    model_path = Path(model_block["model_path"])

    diag_out = _diagnostics_filename(model_path)
    diagnostics = await runner.diagnostics(
        model_path=model_path,
        data_path=data_path,
        output_path=diag_out,
    )
    # Merge diagnostics test p-values into the model parse so persistence
    # + Ljung-Box stay together.
    fit_parsed = dict(model_block["parsed"])
    for k, v in diagnostics.parsed.items():
        if v is not None:
            fit_parsed.setdefault(k, v)

    forecast_out = _forecast_filename(model_path, forecast_horizon)
    forecast = await runner.forecast(
        model_path=model_path,
        horizon=forecast_horizon,
        output_path=forecast_out,
    )

    annual_factor = meta.annualization_factor or annualization_factor_for(
        Frequency(meta.frequency)
    ) or 252

    summary = _summarize_forecast_rows(
        forecast.rows, annualize=True, annualization_factor=annual_factor
    )

    h1_var = summary.get("variances", [None])[0] if summary.get("variances") else None
    h5_var = (
        summary["variances"][min(4, len(summary["variances"]) - 1)]
        if summary.get("variances")
        else None
    )
    h_last_var = summary["variances"][-1] if summary.get("variances") else None

    cum = summary.get("cumulative_variance") or []
    h1_cum = cum[0] if cum else None
    h5_cum = cum[min(4, len(cum) - 1)] if cum else None
    h_last_cum = cum[-1] if cum else None

    unconditional_variance = fit_parsed.get("unconditional_variance")
    unconditional_vol_pp = (
        math.sqrt(unconditional_variance) if isinstance(unconditional_variance, (int, float)) else None
    )
    unconditional_vol_an = (
        unconditional_vol_pp * math.sqrt(annual_factor)
        if unconditional_vol_pp is not None
        else None
    )

    current_cond_vol_pp = (
        math.sqrt(h1_var) if isinstance(h1_var, (int, float)) and h1_var >= 0 else None
    )
    current_cond_vol_an = (
        current_cond_vol_pp * math.sqrt(annual_factor)
        if current_cond_vol_pp is not None
        else None
    )

    distribution_recommendation = _build_distribution_recommendation(
        fit_parsed,
        symbol_or_series=identifier,
        data_path=meta.returns_csv_path,
    )

    payload: dict[str, Any] = {
        "symbol_or_series": identifier,
        "n_observations": meta.output_rows,
        "input_stats": meta.summary_stats,
        "frequency": meta.frequency,
        "annualization_factor": annual_factor,
        "model": {
            "spec": _spec_label(fit_parsed),
            "arima": list(fit_parsed["arima"]) if fit_parsed.get("arima") else None,
            "garch": list(fit_parsed["garch"]) if fit_parsed.get("garch") else None,
            "innovation_used": fit_parsed.get("distribution_used"),
            "params": {
                "intercept": fit_parsed.get("intercept"),
                "ar_coef": fit_parsed.get("ar_coef"),
                "ma_coef": fit_parsed.get("ma_coef"),
                "omega": fit_parsed.get("omega"),
                "alpha_coef": fit_parsed.get("alpha_coef"),
                "beta_coef": fit_parsed.get("beta_coef"),
            },
            "log_likelihood": fit_parsed.get("log_likelihood"),
            "aic": fit_parsed.get("aic"),
            "bic": fit_parsed.get("bic"),
            "persistence": fit_parsed.get("garch_persistence"),
            "near_unit_root": fit_parsed.get("near_unit_root"),
            "mean_reverting": fit_parsed.get("mean_reverting"),
            "unconditional_variance": unconditional_variance,
            "annualized_unconditional_vol": unconditional_vol_an,
        },
        "diagnostics": {
            "ljung_box_pvalue": fit_parsed.get("ljung_box_residuals_pvalue"),
            "ljung_box_sq_pvalue": fit_parsed.get("ljung_box_squared_residuals_pvalue"),
            "jarque_bera_pvalue": fit_parsed.get("jarque_bera_pvalue"),
            "converged": fit_parsed.get("converged"),
        },
        "model_adequate": _model_adequate(fit_parsed),
        "model_adequate_reasons": _model_adequate_reasons(fit_parsed),
        "distribution_recommendation": distribution_recommendation,
        "current_conditional_volatility_per_period": current_cond_vol_pp,
        "current_conditional_volatility_annualized": current_cond_vol_an,
        "forecast": {
            "horizon": forecast_horizon,
            "h1_variance": h1_var,
            "h5_variance": h5_var,
            f"h{forecast_horizon}_variance": h_last_var,
            "h1_cumulative_variance": h1_cum,
            "h5_cumulative_variance": h5_cum,
            f"h{forecast_horizon}_cumulative_variance": h_last_cum,
            "h1_annualized_stdev": summary.get("annualized_stdev", [None])[0]
            if summary.get("annualized_stdev")
            else None,
            "annualized_cumulative_stdev_path": summary.get("annualized_cumulative_stdev"),
            "forecast_csv_path": str(forecast.forecast_csv),
        },
        "artifacts": {
            "returns_csv": meta.returns_csv_path,
            "model_json": str(model_path),
            "diagnostics_json": str(diagnostics.diagnostics_path)
            if diagnostics.diagnostics_path
            else None,
            "forecast_csv": str(forecast.forecast_csv),
        },
        "analyst_summary": _fit_summary(fit_parsed),
    }
    return payload


async def _var_snapshot_impl(
    *,
    identifier: str,
    meta: ReturnsMetadata,
    horizon_days: int,
    confidence: float,
    paths: int,
    portfolio_value: float,
    criterion: SelectionCriterion,
) -> dict[str, Any]:
    runner = get_runner()
    data_path = Path(meta.returns_csv_path)
    stem = safe_filename(identifier) or "series"
    out_model = models_dir() / f"{stem}_var_{criterion.value}.json"
    model_block = await _fit_or_select(
        data_path=data_path,
        out_path=out_model,
        auto_select=True,
        criterion=criterion,
        arima=(1, 0, 1),
        garch=(1, 1),
        innovation=InnovationDist.gaussian,
        t_df=None,
    )
    model_path = Path(model_block["model_path"])
    parsed = model_block["parsed"]

    sim_out = (
        simulations_dir()
        / f"{stem}_var_h{horizon_days}_p{paths}.csv"
    )
    sim = await runner.simulate(
        model_path=model_path,
        paths=paths,
        length=horizon_days,
        output_path=sim_out,
        seed=42,
        stats=True,
    )

    # Forecast for parametric VaR comparison.
    fc_out = _forecast_filename(model_path, horizon_days)
    forecast = await runner.forecast(
        model_path=model_path,
        horizon=horizon_days,
        output_path=fc_out,
    )

    horizon_returns = _terminal_returns_from_simulation_csv(
        Path(sim.simulation_csv), horizon_days
    )

    var_q = 1.0 - confidence
    if not horizon_returns:
        raise AGError(
            f"could not extract terminal returns from {sim.simulation_csv}; "
            "expected one row per (path, t) or wide path columns."
        )

    empirical_var_pct = -_quantile(horizon_returns, var_q)
    below = [r for r in horizon_returns if r <= -empirical_var_pct]
    empirical_es_pct = -(sum(below) / len(below)) if below else None

    fc_summary = _summarize_forecast_rows(
        forecast.rows, annualize=False, annualization_factor=1
    )
    cum_var = fc_summary.get("cumulative_variance") or []
    parametric_var_pct: float | None = None
    if cum_var:
        sigma_h = math.sqrt(cum_var[-1])
        z = _normal_quantile(confidence)
        parametric_var_pct = z * sigma_h

    fat_tail_uplift = (
        empirical_var_pct / parametric_var_pct
        if parametric_var_pct and parametric_var_pct > 0
        else None
    )

    warnings: list[str] = []
    distribution_used = parsed.get("distribution_used") or "gaussian"
    if (
        distribution_used == "gaussian"
        and parsed.get("student_t_recommended")
    ):
        warnings.append(
            "Model uses Gaussian innovations but Student-t was recommended; "
            "empirical VaR is likely more reliable than parametric VaR."
        )
    if parsed.get("near_unit_root"):
        warnings.append(
            "GARCH persistence is at/near 1.0; multi-day forecast variance "
            "does not converge and VaR may be wildly path-dependent."
        )
    if not _model_adequate(parsed):
        warnings.extend(_model_adequate_reasons(parsed))

    payload = {
        "symbol": identifier,
        "horizon_days": horizon_days,
        "confidence": confidence,
        "paths": paths,
        "portfolio_value": portfolio_value,
        "empirical_var": empirical_var_pct,
        "empirical_es": empirical_es_pct,
        "parametric_var": parametric_var_pct,
        "empirical_var_dollars": empirical_var_pct * portfolio_value,
        "empirical_es_dollars": (
            empirical_es_pct * portfolio_value if empirical_es_pct is not None else None
        ),
        "parametric_var_dollars": (
            parametric_var_pct * portfolio_value if parametric_var_pct is not None else None
        ),
        "distribution_assumption": distribution_used,
        "fat_tail_uplift": fat_tail_uplift,
        "model_adequate": _model_adequate(parsed),
        "warnings": warnings,
        "artifacts": {
            "model_json": str(model_path),
            "simulation_csv": str(sim.simulation_csv),
            "forecast_csv": str(forecast.forecast_csv),
        },
        "analyst_summary": (
            f"{identifier} {horizon_days}d {confidence:.0%} VaR: "
            f"empirical {empirical_var_pct:.4f} vs parametric "
            f"{parametric_var_pct:.4f} (fat-tail uplift "
            f"{fat_tail_uplift:.2f}× when defined)."
            if parametric_var_pct
            else f"{identifier} {horizon_days}d {confidence:.0%} empirical VaR: {empirical_var_pct:.4f}."
        ),
    }
    return payload


async def _forecast_distribution_impl(
    *,
    token: str,
    horizon: int,
    paths: int,
    period: str,
    criterion: SelectionCriterion,
    seed: int,
) -> dict[str, Any]:
    candidate = Path(token).expanduser()
    if candidate.exists() and candidate.suffix.lower() == ".json":
        model_path = candidate
        parsed = load_model(candidate)
        identifier = candidate.stem
    else:
        years_back = _years_back_from_period(period)
        from_d, to_d = _period_default_dates(years_back)
        meta = await _load_series_impl(
            source="fmp_prices",
            identifier=token,
            from_date=from_d,
            to_date=to_d,
            return_type=ReturnType.log,
            price_column="adjClose",
        )
        data_path = Path(meta.returns_csv_path)
        identifier = token
        stem = safe_filename(token) or "series"
        out_model = models_dir() / f"{stem}_distfan_{criterion.value}.json"
        model_block = await _fit_or_select(
            data_path=data_path,
            out_path=out_model,
            auto_select=True,
            criterion=criterion,
            arima=(1, 0, 1),
            garch=(1, 1),
            innovation=InnovationDist.gaussian,
            t_df=None,
        )
        model_path = Path(model_block["model_path"])
        parsed = model_block["parsed"]

    runner = get_runner()
    sim_out = simulations_dir() / f"{safe_filename(identifier)}_distfan_p{paths}_h{horizon}.csv"
    sim = await runner.simulate(
        model_path=model_path,
        paths=paths,
        length=horizon,
        output_path=sim_out,
        seed=seed,
        stats=False,
    )

    quantiles = _quantile_fan_from_csv(Path(sim.simulation_csv), horizon, paths)
    return {
        "identifier": identifier,
        "model_path": str(model_path),
        "horizon": horizon,
        "paths": paths,
        "seed": seed,
        "quantiles": quantiles,
        "model_adequate": _model_adequate(parsed) if parsed else None,
        "artifacts": {
            "simulation_csv": str(sim.simulation_csv),
            "model_json": str(model_path),
        },
    }


async def _compare_volatility_impl(
    *,
    symbols: list[str],
    period: str,
    criterion: SelectionCriterion | Literal["fixed"],
) -> dict[str, Any]:
    years_back = _years_back_from_period(period)
    from_d, to_d = _period_default_dates(years_back)
    runner = get_runner()
    table: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            meta = await _load_series_impl(
                source="fmp_prices",
                identifier=symbol,
                from_date=from_d,
                to_date=to_d,
                return_type=ReturnType.log,
                price_column="adjClose",
            )
            data_path = Path(meta.returns_csv_path)
            out_model = models_dir() / f"{safe_filename(symbol)}_compare.json"
            if criterion == "fixed":
                fit = await runner.fit(
                    data_path=data_path,
                    arima=(1, 0, 1),
                    garch=(1, 1),
                    output_path=out_model,
                )
                parsed = fit.parsed
            else:
                sel = await runner.select(
                    data_path=data_path,
                    output_path=out_model,
                    criterion=criterion.value,
                )
                parsed = sel.parsed
            af = meta.annualization_factor or 252
            persistence = parsed.get("garch_persistence")
            uncond_var = parsed.get("unconditional_variance")
            uncond_vol_an = (
                math.sqrt(uncond_var) * math.sqrt(af)
                if isinstance(uncond_var, (int, float)) and uncond_var > 0
                else None
            )
            realized_vol_an = (
                (meta.summary_stats.get("stdev") or 0.0) * math.sqrt(af)
                if meta.summary_stats.get("stdev")
                else None
            )
            table.append(
                {
                    "symbol": symbol,
                    "n_obs": meta.output_rows,
                    "annualized_realized_vol": realized_vol_an,
                    "annualized_unconditional_vol": uncond_vol_an,
                    "persistence": persistence,
                    "near_unit_root": parsed.get("near_unit_root"),
                    "distribution_used": parsed.get("distribution_used"),
                    "student_t_recommended": parsed.get("student_t_recommended"),
                    "excess_kurtosis_input": meta.summary_stats.get("excess_kurtosis"),
                    "model_adequate": _model_adequate(parsed),
                    "model_path": str(out_model),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"symbol": symbol, "error": str(exc)})
    table.sort(
        key=lambda r: (-(r["persistence"] or -1.0), r["symbol"]),
    )
    return {
        "symbols": symbols,
        "period": period,
        "criterion": criterion if isinstance(criterion, str) else criterion.value,
        "rows": table,
        "errors": errors,
    }


async def _stress_test_impl(
    *,
    identifier: str,
    meta: ReturnsMetadata,
    scenario: Literal["gaussian", "student_t_df5", "student_t_df3"],
    horizon_days: int,
    paths: int,
) -> dict[str, Any]:
    runner = get_runner()
    if scenario == "gaussian":
        innovation = "gaussian"
        t_df = None
    elif scenario == "student_t_df5":
        innovation = "student_t"
        t_df = 5.0
    elif scenario == "student_t_df3":
        innovation = "student_t"
        t_df = 3.0
    else:
        raise AGError(f"unknown scenario {scenario!r}")

    out_model = (
        models_dir()
        / f"{safe_filename(identifier)}_stress_{scenario}.json"
    )
    data_path = Path(meta.returns_csv_path)
    fit = await runner.fit(
        data_path=data_path,
        arima=(1, 0, 1),
        garch=(1, 1),
        innovation=innovation,
        t_df=t_df,
        output_path=out_model,
    )
    sim_out = (
        simulations_dir()
        / f"{safe_filename(identifier)}_stress_{scenario}_h{horizon_days}_p{paths}.csv"
    )
    sim = await runner.simulate(
        model_path=out_model,
        paths=paths,
        length=horizon_days,
        output_path=sim_out,
        seed=42,
        stats=True,
    )

    horizon_returns = _terminal_returns_from_simulation_csv(
        Path(sim.simulation_csv), horizon_days
    )
    if not horizon_returns:
        raise AGError(
            f"could not extract terminal returns from {sim.simulation_csv}."
        )

    percentiles = [0.01, 0.05, 0.10, 0.50, 0.90, 0.95, 0.99]
    dist = {f"p{int(p * 100):02d}": _quantile(horizon_returns, p) for p in percentiles}

    prob_loss_gt_5 = sum(1 for r in horizon_returns if r <= -0.05) / len(horizon_returns)
    prob_loss_gt_10 = sum(1 for r in horizon_returns if r <= -0.10) / len(horizon_returns)
    prob_loss_gt_20 = sum(1 for r in horizon_returns if r <= -0.20) / len(horizon_returns)

    return {
        "symbol": identifier,
        "scenario": scenario,
        "horizon_days": horizon_days,
        "paths": paths,
        "return_distribution": dist,
        "prob_loss_gt_5pct": prob_loss_gt_5,
        "prob_loss_gt_10pct": prob_loss_gt_10,
        "prob_loss_gt_20pct": prob_loss_gt_20,
        "worst_terminal_return": min(horizon_returns),
        "best_terminal_return": max(horizon_returns),
        "model": {
            "innovation_used": fit.parsed.get("distribution_used"),
            "t_df": t_df,
            "spec": _spec_label(fit.parsed),
            "persistence": fit.parsed.get("garch_persistence"),
        },
        "artifacts": {
            "simulation_csv": str(sim.simulation_csv),
            "model_json": str(out_model),
        },
        "analyst_summary": (
            f"{identifier} {horizon_days}d {scenario}: "
            f"P(loss>5%)={prob_loss_gt_5:.2%}, "
            f"P(loss>10%)={prob_loss_gt_10:.2%}, "
            f"P(loss>20%)={prob_loss_gt_20:.2%}; "
            f"1%/5% tails {dist['p01']:.4f}/{dist['p05']:.4f}."
        ),
    }


# ---------- simulation-CSV helpers ----------------------------------------


def _terminal_returns_from_simulation_csv(path: Path, horizon: int) -> list[float]:
    """Read the simulation CSV and return one cumulative log return per path.

    Tolerates either of two common shapes:

    - **Long format**: columns ``path, t, value``. We group by ``path``,
      sum log-return values within each group.
    - **Wide format**: one column per path (``path_0, path_1, ...`` or
      numeric column names). We sum each path column.
    """
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        raise AGError(f"could not read simulation CSV {path}: {exc}") from exc
    if df.empty:
        return []
    cols = [c.lower() for c in df.columns]
    if "path" in cols and ("value" in cols or "return" in cols or "y" in cols):
        df.columns = cols
        value_col = "value" if "value" in cols else ("return" if "return" in cols else "y")
        terminals: list[float] = []
        for _, grp in df.groupby("path"):
            terminals.append(float(grp[value_col].sum()))
        return terminals
    # Wide format: each non-meta column is a path.
    meta_cols = {"t", "step", "horizon", "time", "h"}
    path_cols = [c for c in df.columns if c.lower() not in meta_cols]
    if not path_cols:
        return []
    sums = df[path_cols].sum(axis=0).tolist()
    return [float(x) for x in sums]


def _quantile_fan_from_csv(path: Path, horizon: int, paths: int) -> list[dict[str, Any]]:
    """Build [5,10,25,50,75,90,95] quantiles at each step.

    Same long/wide tolerance as :func:`_terminal_returns_from_simulation_csv`.
    """
    df = pd.read_csv(path)
    if df.empty:
        return []
    cols = [c.lower() for c in df.columns]
    df.columns = cols
    qs = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    if "path" in cols and "t" in cols and ("value" in cols or "return" in cols):
        value_col = "value" if "value" in cols else "return"
        out: list[dict[str, Any]] = []
        for t, grp in df.groupby("t"):
            row: dict[str, Any] = {"t": int(t)}
            for q in qs:
                row[f"q{int(q * 100):02d}"] = float(grp[value_col].quantile(q))
            out.append(row)
        return out
    meta_cols = {"t", "step", "horizon", "time", "h"}
    path_cols = [c for c in df.columns if c not in meta_cols]
    out2: list[dict[str, Any]] = []
    for i, row in df.iterrows():
        rec: dict[str, Any] = {"t": int(i) + 1}
        vals = pd.to_numeric(row[path_cols], errors="coerce").dropna()
        for q in qs:
            rec[f"q{int(q * 100):02d}"] = float(vals.quantile(q))
        out2.append(rec)
    return out2


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise AGError("cannot compute quantile of empty sequence.")
    return float(pd.Series(values).quantile(q))
