"""Primitive 1:1 MCP wrappers for `ag` subcommands.

Each tool surfaces one CLI subcommand and bundles:

- File paths to every artifact written (model JSON, forecast CSV, etc.).
- A flat ``parsed`` block produced by :mod:`ag_mcp.interpretation` so the
  LLM never has to scrape the CLI's free-text report.
- A short ``analyst_summary`` string the LLM can quote verbatim.
- The CLI's full ``raw_stdout`` text for transparency / debugging.

These are the building blocks the composite tools call. Every analyst-
visible string follows the same convention: log returns for prices,
explicit annualization factor, persistence flagged when near 1.0.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..errors import AGError
from ..models import (
    ArimaOrder,
    DataPath,
    GarchOrder,
    InnovationDist,
    Label,
    ModelPath,
    OutputMode,
    ResponseFormat,
    SelectionCriterion,
)
from ..output import (
    diagnostics_dir,
    forecasts_dir,
    models_dir,
    safe_filename,
    simulations_dir,
    spec_string,
)
from ..registry import list_models, load_model
from ..runner import get_runner
from ._common import READ_ONLY, render_small_result, wrap_error


# ---------- naming helpers -----------------------------------------------


def _short_hash(*parts: str) -> str:
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:8]


def _model_filename(
    *,
    label: str | None,
    data_path: Path,
    arima: tuple[int, int, int],
    garch: tuple[int, int],
    innovation: str,
) -> Path:
    stem = label or safe_filename(data_path.stem)
    spec = spec_string(arima, garch)
    h = _short_hash(str(data_path), spec, innovation)
    return models_dir() / f"{stem}_{spec}_{innovation}_{h}.json"


def _forecast_filename(model_path: Path, horizon: int) -> Path:
    return forecasts_dir() / f"{model_path.stem}_h{horizon}.csv"


def _simulation_filename(model_path: Path, paths: int, length: int, seed: int) -> Path:
    return simulations_dir() / (
        f"{model_path.stem}_paths{paths}_len{length}_seed{seed}.csv"
    )


def _diagnostics_filename(model_path: Path) -> Path:
    return diagnostics_dir() / f"{model_path.stem}_diagnostics.json"


# ---------- analyst-summary helpers --------------------------------------


def _spec_label(parsed: dict[str, Any]) -> str:
    arima = parsed.get("arima")
    garch = parsed.get("garch")
    inn = parsed.get("distribution_used") or "gaussian"
    if not arima or not garch:
        return f"ARIMA-GARCH ({inn})"
    p, d, q = arima
    gp, gq = garch
    return f"ARIMA({p},{d},{q})-GARCH({gp},{gq}) [{inn}]"


def _persistence_label(parsed: dict[str, Any]) -> str:
    p = parsed.get("garch_persistence")
    if p is None:
        return "persistence unknown"
    if p > 0.999:
        return f"persistence {p:.3f} (near unit root — multi-step variance does not converge)"
    if p > 0.95:
        return f"persistence {p:.3f} (highly persistent)"
    return f"persistence {p:.3f} (mean-reverting)"


def _fit_summary(parsed: dict[str, Any]) -> str:
    parts: list[str] = [_spec_label(parsed)]
    conv = parsed.get("converged")
    if conv is False:
        parts.append("DID NOT converge")
    elif conv is True:
        parts.append("Converged")
    parts.append(_persistence_label(parsed))
    lb2 = parsed.get("ljung_box_squared_residuals_pvalue")
    if lb2 is not None:
        flag = "good" if lb2 > 0.05 else "rejects: residual ARCH"
        parts.append(f"Ljung-Box² p={lb2:.3g} ({flag})")
    jb = parsed.get("jarque_bera_pvalue")
    if jb is not None:
        flag = "normal" if jb > 0.05 else "non-normal residuals"
        parts.append(f"JB p={jb:.3g} ({flag})")
    if parsed.get("student_t_recommended"):
        df = parsed.get("student_t_df_suggested")
        df_str = f" (suggested df≈{df:.2f})" if df else ""
        parts.append(f"Student-t recommended{df_str}")
    return ". ".join(parts) + "."


# ---------- registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="ag_fit",
        annotations=READ_ONLY,
        description=(
            "Fit a specific ARIMA(p,d,q)-GARCH(p,q) model to a returns CSV "
            "via `ag fit`. data_path must be a single-column CSV produced "
            "by ag_prepare_returns or ag_load_series (or already-stationary "
            "data of your own). innovation='gaussian' is the default; pass "
            "'student_t' (and optionally t_df) to model heavy tails. "
            "Returns: model_path (saved JSON under $AG_OUTPUT_DIR/models/), "
            "the flat 'parsed' block (params, persistence, test p-values, "
            "Student-t recommendation), an analyst_summary string, and the "
            "CLI's raw_stdout. WRITES one model JSON; no other side-effects."
        ),
    )
    async def ag_fit(
        data_path: Annotated[DataPath, Field(description="Returns CSV (one numeric column).")],
        arima: Annotated[ArimaOrder, Field(description="ARIMA (p,d,q) order, e.g. [1,0,1].")],
        garch: Annotated[GarchOrder, Field(description="GARCH (p,q) order, e.g. [1,1].")],
        innovation: Annotated[
            InnovationDist,
            Field(description="gaussian (default) or student_t."),
        ] = InnovationDist.gaussian,
        t_df: Annotated[
            float | None,
            Field(description="Student-t degrees of freedom (only when innovation=student_t)."),
        ] = None,
        label: Label = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown (default) or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            out_path = _model_filename(
                label=label,
                data_path=Path(data_path),
                arima=arima,
                garch=garch,
                innovation=innovation.value,
            )
            result = await get_runner().fit(
                data_path=Path(data_path),
                arima=arima,
                garch=garch,
                output_path=out_path,
                innovation=innovation.value,
                t_df=t_df,
            )
            payload = {
                "model_path": str(result.model_path),
                "parsed": result.parsed,
                "analyst_summary": _fit_summary(result.parsed),
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": {"model_json": str(result.model_path)},
            }
            return render_small_result(
                payload,
                response_format,
                title=f"ag fit: {Path(data_path).stem}",
                what="ag_fit",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_select",
        annotations=READ_ONLY,
        description=(
            "Search the ARIMA-GARCH grid under a chosen information "
            "criterion via `ag select`. Defaults: max_p=2, max_d=1, "
            "max_q=2, max_garch_p=1, max_garch_q=1, criterion='BIC' "
            "(fast). criterion='CV' fits all combos with held-out cross-"
            "validation — slow; budget several minutes and the connector "
            "will timeout if it exceeds $AG_SUBPROCESS_TIMEOUT (600s "
            "default). Returns the winning model JSON path, the flat "
            "parsed block, and an analyst_summary. WRITES one model JSON."
        ),
    )
    async def ag_select(
        data_path: Annotated[DataPath, Field(description="Returns CSV (one numeric column).")],
        max_p: Annotated[int, Field(description="Max ARIMA p (default 2).", ge=0, le=5)] = 2,
        max_d: Annotated[int, Field(description="Max ARIMA d (default 1).", ge=0, le=2)] = 1,
        max_q: Annotated[int, Field(description="Max ARIMA q (default 2).", ge=0, le=5)] = 2,
        max_garch_p: Annotated[int, Field(description="Max GARCH p (default 1).", ge=0, le=3)] = 1,
        max_garch_q: Annotated[int, Field(description="Max GARCH q (default 1).", ge=0, le=3)] = 1,
        criterion: Annotated[
            SelectionCriterion,
            Field(description="BIC (default), AIC, AICc, or CV (slow)."),
        ] = SelectionCriterion.BIC,
        top_k: Annotated[
            int | None,
            Field(description="If set, also print the top-k candidates to stdout."),
        ] = None,
        label: Label = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            stem = label or safe_filename(Path(data_path).stem)
            out_path = models_dir() / f"{stem}_selected_{criterion.value}.json"
            result = await get_runner().select(
                data_path=Path(data_path),
                output_path=out_path,
                max_p=max_p,
                max_d=max_d,
                max_q=max_q,
                max_garch_p=max_garch_p,
                max_garch_q=max_garch_q,
                criterion=criterion.value,
                top_k=top_k,
            )
            payload = {
                "model_path": str(result.model_path),
                "criterion": criterion.value,
                "parsed": result.parsed,
                "analyst_summary": "Selected " + _fit_summary(result.parsed),
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": {"model_json": str(result.model_path)},
            }
            return render_small_result(
                payload,
                response_format,
                title=f"ag select ({criterion.value}): {stem}",
                what="ag_select",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_forecast",
        annotations=READ_ONLY,
        description=(
            "Multi-step conditional-mean and conditional-variance forecast "
            "from a saved model JSON via `ag forecast`. horizon is in the "
            "model's own time unit (typically the same cadence as the "
            "training data — e.g. trading days for daily returns). When "
            "annualize=True, the returned summary multiplies forecast "
            "variance by annualization_factor (252 for daily) and reports "
            "annualized stdev; the persisted CSV is always per-period. "
            "Mode inline (default) returns rows; mode summary returns a "
            "digest with the CSV path."
        ),
    )
    async def ag_forecast(
        model_path: Annotated[ModelPath, Field(description="Saved model JSON path.")],
        horizon: Annotated[int, Field(description="Number of forecast steps.", ge=1, le=2000)],
        annualize: Annotated[
            bool,
            Field(description="If true, also report annualized stdev in the summary."),
        ] = False,
        annualization_factor: Annotated[
            int,
            Field(description="Steps per year (252 daily, 12 monthly, 4 quarterly).", ge=1),
        ] = 252,
        mode: Annotated[
            OutputMode,
            Field(description="inline (default) returns rows; summary returns a digest."),
        ] = OutputMode.inline,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            mp = Path(model_path)
            out_path = _forecast_filename(mp, horizon)
            result = await get_runner().forecast(
                model_path=mp,
                horizon=horizon,
                output_path=out_path,
            )
            summary = _summarize_forecast_rows(
                result.rows,
                annualize=annualize,
                annualization_factor=annualization_factor,
            )
            payload: dict[str, Any] = {
                "model_path": str(mp),
                "horizon": horizon,
                "forecast_csv_path": str(result.forecast_csv),
                "summary": summary,
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": {"forecast_csv": str(result.forecast_csv)},
            }
            if mode == OutputMode.inline:
                payload["rows"] = result.rows
            return render_small_result(
                payload,
                response_format,
                title=f"ag forecast h={horizon}: {mp.stem}",
                what="ag_forecast",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_simulate",
        annotations=READ_ONLY,
        description=(
            "Monte Carlo simulation from a saved model JSON via `ag "
            "simulate`. Generates `paths` paths of length `length`, "
            "seeding from `seed`. With stats=True the CLI prints summary "
            "statistics to stdout. mode='summary' (default) returns a "
            "digest and writes the full simulation CSV to disk; "
            "mode='inline' caps the inline payload at 5000 rows. Output "
            "size is paths * length cells — use summary mode for anything "
            "large."
        ),
    )
    async def ag_simulate(
        model_path: Annotated[ModelPath, Field(description="Saved model JSON path.")],
        paths: Annotated[int, Field(description="Number of simulated paths.", ge=1, le=100000)],
        length: Annotated[int, Field(description="Steps per path.", ge=1, le=10000)],
        seed: Annotated[int, Field(description="RNG seed (default 42).")] = 42,
        stats: Annotated[bool, Field(description="Print summary stats to stdout.")] = True,
        mode: Annotated[
            OutputMode,
            Field(description="summary (default) writes CSV; inline returns rows capped at 5000."),
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            mp = Path(model_path)
            out_path = _simulation_filename(mp, paths, length, seed)
            result = await get_runner().simulate(
                model_path=mp,
                paths=paths,
                length=length,
                output_path=out_path,
                seed=seed,
                stats=stats,
            )
            payload: dict[str, Any] = {
                "model_path": str(mp),
                "paths": paths,
                "length": length,
                "seed": seed,
                "simulation_csv_path": str(result.simulation_csv),
                "stats": result.parsed_stats,
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": {"simulation_csv": str(result.simulation_csv)},
            }
            if mode == OutputMode.inline:
                rows = get_runner()._read_csv_rows(result.simulation_csv)
                if len(rows) > 5000:
                    payload["rows"] = rows[:5000]
                    payload["row_cap"] = 5000
                    payload["total_rows"] = len(rows)
                    payload["note"] = (
                        "inline rows capped at 5000; switch to mode=summary "
                        "for the full simulation."
                    )
                else:
                    payload["rows"] = rows
                    payload["total_rows"] = len(rows)
            return render_small_result(
                payload,
                response_format,
                title=f"ag simulate ({paths}×{length}): {mp.stem}",
                what="ag_simulate",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_diagnostics",
        annotations=READ_ONLY,
        description=(
            "Post-fit diagnostics via `ag diagnostics`: Ljung-Box on raw "
            "and squared residuals, Jarque-Bera normality, and whatever "
            "else the CLI emits. data_path must be the same returns CSV "
            "the model was fitted on. Writes a diagnostics JSON to "
            "$AG_OUTPUT_DIR/diagnostics/. Key fields in 'parsed': "
            "ljung_box_residuals_pvalue, ljung_box_squared_residuals_pvalue "
            "(the GARCH-adequacy gate — > 0.05 is good), jarque_bera_pvalue."
        ),
    )
    async def ag_diagnostics(
        model_path: Annotated[ModelPath, Field(description="Saved model JSON path.")],
        data_path: Annotated[DataPath, Field(description="Same returns CSV used to fit.")],
        write_json: Annotated[
            bool,
            Field(description="If true, also write a diagnostics JSON file."),
        ] = True,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            mp = Path(model_path)
            out_path = _diagnostics_filename(mp) if write_json else None
            result = await get_runner().diagnostics(
                model_path=mp,
                data_path=Path(data_path),
                output_path=out_path,
            )
            payload: dict[str, Any] = {
                "model_path": str(mp),
                "data_path": str(data_path),
                "parsed": result.parsed,
                "diagnostics_path": (
                    str(result.diagnostics_path) if result.diagnostics_path else None
                ),
                "model_adequate": _model_adequate(result.parsed),
                "model_adequate_reasons": _model_adequate_reasons(result.parsed),
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": (
                    {"diagnostics_json": str(result.diagnostics_path)}
                    if result.diagnostics_path
                    else {}
                ),
            }
            return render_small_result(
                payload,
                response_format,
                title=f"ag diagnostics: {mp.stem}",
                what="ag_diagnostics",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_describe_model",
        annotations=READ_ONLY,
        description=(
            "Read a saved model JSON and return its spec, params, "
            "persistence, near-unit-root flag, unconditional variance, "
            "and creation time. Pure local file read — no subprocess. "
            "Use this to inspect a model produced by ag_fit/ag_select "
            "before forecasting or simulating with it."
        ),
    )
    async def ag_describe_model(
        model_path: Annotated[ModelPath, Field(description="Saved model JSON path.")],
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            info = load_model(Path(model_path))
            return render_small_result(
                {
                    "path": info["path"],
                    "label": info["label"],
                    "spec": {
                        "arima": info.get("arima"),
                        "garch": info.get("garch"),
                        "innovation": info.get("distribution_used"),
                        "t_df": info.get("t_df"),
                    },
                    "params": {
                        "intercept": info.get("intercept"),
                        "ar_coef": info.get("ar_coef"),
                        "ma_coef": info.get("ma_coef"),
                        "omega": info.get("omega"),
                        "alpha_coef": info.get("alpha_coef"),
                        "beta_coef": info.get("beta_coef"),
                    },
                    "fit_quality": {
                        "log_likelihood": info.get("log_likelihood"),
                        "aic": info.get("aic"),
                        "bic": info.get("bic"),
                        "aicc": info.get("aicc"),
                        "converged": info.get("converged"),
                    },
                    "garch_persistence": info.get("garch_persistence"),
                    "near_unit_root": info.get("near_unit_root"),
                    "mean_reverting": info.get("mean_reverting"),
                    "unconditional_variance": info.get("unconditional_variance"),
                    "analyst_summary": _fit_summary(info),
                },
                response_format,
                title=f"Model: {Path(model_path).stem}",
                what="ag_describe_model",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_list_models",
        annotations=READ_ONLY,
        description=(
            "List every fitted model JSON under $AG_OUTPUT_DIR/models/. "
            "Returns one summary entry per file with path, label, spec "
            "(arima/garch), persistence, log-likelihood, AIC/BIC, "
            "convergence flag, and the file's mtime. Pure local scan — "
            "no subprocess."
        ),
    )
    async def ag_list_models(
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            models = list_models()
            return render_small_result(
                {"count": len(models), "models": models},
                response_format,
                title="Saved AG models",
                what="ag_list_models",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_sim_from_spec",
        annotations=READ_ONLY,
        description=(
            "Synthesize a returns series from a bare ARIMA(p,d,q)-GARCH"
            "(p,q) spec via `ag sim`. No model JSON required. Useful for "
            "tests, didactic demos, and stress-test 'what would a process "
            "with these parameters look like?' explorations. Writes a "
            "single-column CSV usable as input to ag_fit."
        ),
    )
    async def ag_sim_from_spec(
        arima: Annotated[ArimaOrder, Field(description="ARIMA (p,d,q) order.")],
        garch: Annotated[GarchOrder, Field(description="GARCH (p,q) order.")],
        length: Annotated[int, Field(description="Number of observations to synthesize.", ge=2, le=100000)],
        seed: Annotated[int, Field(description="RNG seed (default 42).")] = 42,
        innovation: Annotated[
            InnovationDist,
            Field(description="gaussian (default) or student_t."),
        ] = InnovationDist.gaussian,
        t_df: Annotated[
            float | None,
            Field(description="Student-t df (only when innovation=student_t)."),
        ] = None,
        label: Label = None,
        mode: Annotated[
            OutputMode,
            Field(description="summary (default) returns digest; inline returns rows."),
        ] = OutputMode.summary,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            from ..output import returns_dir

            stem = label or f"synth_{spec_string(arima, garch)}_{innovation.value}_seed{seed}_n{length}"
            out_path = returns_dir() / f"{safe_filename(stem)}.csv"
            result = await get_runner().sim(
                arima=arima,
                garch=garch,
                length=length,
                output_path=out_path,
                seed=seed,
                innovation=innovation.value,
                t_df=t_df,
            )
            payload: dict[str, Any] = {
                "data_csv_path": str(result.data_csv),
                "arima": list(arima),
                "garch": list(garch),
                "length": length,
                "seed": seed,
                "innovation": innovation.value,
                "t_df": t_df,
                "raw_stdout": result.raw_stdout,
                "argv": result.argv,
                "artifacts": {"data_csv": str(result.data_csv)},
            }
            if mode == OutputMode.inline:
                payload["rows"] = get_runner()._read_csv_rows(result.data_csv)[:5000]
            return render_small_result(
                payload,
                response_format,
                title=f"ag sim: {stem}",
                what="ag_sim_from_spec",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)


# ---------- forecast summarizer ------------------------------------------


def _summarize_forecast_rows(
    rows: list[dict[str, Any]],
    *,
    annualize: bool,
    annualization_factor: int,
) -> dict[str, Any]:
    """Build the analyst-friendly summary from `ag forecast`'s CSV rows.

    Columns expected: ``horizon`` (or ``step``/``h``), ``mean``,
    ``variance`` (or ``var``), and optionally ``lower_95``/``upper_95``.
    We look for the common label variants and ignore anything we don't
    recognize — the LLM still has access to the full CSV.
    """
    if not rows:
        return {"horizons": 0}

    def _get(row: dict[str, Any], *keys: str) -> float | None:
        for k in keys:
            v = row.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None

    horizons: list[int] = []
    means: list[float] = []
    variances: list[float] = []
    for r in rows:
        h = _get(r, "horizon", "step", "h", "t")
        if h is not None:
            horizons.append(int(h))
        m = _get(r, "mean", "forecast", "mu")
        if m is not None:
            means.append(m)
        v = _get(r, "variance", "var", "sigma2", "conditional_variance")
        if v is not None:
            variances.append(v)

    summary: dict[str, Any] = {
        "horizons": len(rows),
        "means": means,
        "variances": variances,
    }
    if variances:
        sigma_pp = [v**0.5 for v in variances]
        summary["per_period_stdev"] = sigma_pp
        if annualize:
            summary["annualization_factor"] = annualization_factor
            summary["annualized_stdev"] = [
                s * (annualization_factor**0.5) for s in sigma_pp
            ]
            # Cumulative variance at horizon h (sum of step variances) is
            # the relevant scale for a horizon-h return; annualize that too.
            cum_var = []
            running = 0.0
            for v in variances:
                running += v
                cum_var.append(running)
            summary["cumulative_variance"] = cum_var
            summary["annualized_cumulative_stdev"] = [
                (cv * annualization_factor) ** 0.5 for cv in cum_var
            ]
    return summary


# ---------- model-adequacy helpers (also used by composites) -------------


def _model_adequate(parsed: dict[str, Any]) -> bool:
    lb2 = parsed.get("ljung_box_squared_residuals_pvalue")
    persistence = parsed.get("garch_persistence")
    if lb2 is not None and lb2 <= 0.05:
        return False
    if persistence is not None and persistence >= 0.999:
        return False
    converged = parsed.get("converged")
    if converged is False:
        return False
    return True


def _model_adequate_reasons(parsed: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    lb2 = parsed.get("ljung_box_squared_residuals_pvalue")
    if lb2 is not None and lb2 <= 0.05:
        reasons.append(
            f"Ljung-Box on squared residuals p={lb2:.3g} rejects: residual ARCH remains."
        )
    persistence = parsed.get("garch_persistence")
    if persistence is not None and persistence >= 0.999:
        reasons.append(
            f"GARCH persistence {persistence:.4f} is at/above unit root: "
            "multi-step variance forecasts do not converge."
        )
    if parsed.get("converged") is False:
        reasons.append("Optimizer did NOT converge.")
    return reasons
