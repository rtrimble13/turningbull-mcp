"""Primitive 1:1 MCP wrappers for each `po` CLI subcommand.

Each tool surfaces one CLI subcommand and bundles:

- The path to the JSON/CSV artifact `po` wrote.
- A flat ``weights`` dict (``{ticker: weight}``) extracted from the JSON.
- A ``metrics`` block (expected return, volatility, Sharpe, diversification
  ratio, effective N, tracking error, …) extracted from the JSON.
- Solver/constraint ``diagnostics`` (when present).
- The CLI's full ``raw_stdout`` text for transparency / debugging.

These are the building blocks the composite tools call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..errors import POError
from ..models import (
    AssetDataInline,
    BlackLittermanParams,
    DataPathInput,
    OptimizationParams,
    OutputFormat,
    ResponseFormat,
    Shrinkage,
    Label,
    materialize_data,
    materialize_params,
)
from ..output import (
    content_hash,
    frontiers_dir,
    label_or_hash,
    reports_dir,
    results_dir,
)
from ..runner import get_runner
from ._common import READ_ONLY, render_small_result, wrap_error


# ---------- input handling ----------------------------------------------


def _resolve_data_input(
    data: dict[str, Any] | None,
    data_path: str | None,
) -> Path:
    """Materialize one of (inline data, file path) into a Path on disk.

    Exactly one must be provided. Inline payloads are validated against
    :class:`AssetDataInline` (so the LLM gets a clear error on malformed
    schemas) then content-addressed under ``$PO_OUTPUT_DIR/tmp/``.
    """
    if (data is None) == (data_path is None):
        raise POError(
            "Provide exactly one of `data` (inline JSON) or `data_path` "
            "(path to an assets.json or returns CSV on disk)."
        )
    if data is not None:
        validated = AssetDataInline.model_validate(
            {**{k: v for k, v in data.items() if k != "kind"}, "kind": "inline"}
        )
        return materialize_data(validated)
    return materialize_data(DataPathInput(path=Path(data_path)))  # type: ignore[arg-type]


def _resolve_params_input(
    params: dict[str, Any] | None,
    *,
    kind: Literal["mvo", "bl"],
) -> Path | None:
    """Validate + materialize an OptimizationParams / BlackLittermanParams payload."""
    if params is None:
        return None
    model_cls = OptimizationParams if kind == "mvo" else BlackLittermanParams
    validated = model_cls.model_validate(params)
    return materialize_params(validated, kind=kind)


def _result_filename(method: str, label: str | None, *parts: str) -> Path:
    stem = label_or_hash(label, method, *parts)
    return results_dir() / f"{method}_{stem}.json"


def _frontier_filename(method: str, label: str | None, *parts: str) -> Path:
    stem = label_or_hash(label, method, *parts)
    return frontiers_dir() / f"{method}_{stem}.csv"


def _data_token(data: dict | None, data_path: str | None) -> str:
    """Short hash representing the chosen data input (for filenames)."""
    if data is not None:
        import json as _json
        return content_hash(_json.dumps(data, sort_keys=True, default=str))
    return content_hash(str(data_path))


# ---------- shared parameter annotations --------------------------------


_DataInlineField = Annotated[
    dict[str, Any] | None,
    Field(
        default=None,
        description=(
            "Inline assets payload. Schema: "
            "{assets: [{ticker, expected_return?, sector?, market_cap?, ...}], "
            "covariance: [[...]], market_weights?, benchmark_weights?, "
            "risk_free_rate?}. Materialized to "
            "$PO_OUTPUT_DIR/tmp/<content-hash>.json before `po` is invoked. "
            "Provide either this or `data_path`, not both."
        ),
    ),
]

_DataPathField = Annotated[
    str | None,
    Field(
        default=None,
        description=(
            "Path to an existing assets.json (or returns CSV when --returns is "
            "set) on disk. Provide either this or `data`, not both."
        ),
    ),
]

_ParamsField = Annotated[
    dict[str, Any] | None,
    Field(
        default=None,
        description=(
            "Optional MVO constraints / overrides. Schema mirrors `po`'s "
            "params JSON: lower_bounds, upper_bounds (dict[ticker, float] | "
            "list | float), budget, current_weights, turnover_penalty, "
            "tracking_error_limit, gross_exposure_limit, groups "
            "([{members: [tickers], lower, upper}]), risk_aversion, "
            "frontier_points."
        ),
    ),
]

_BLParamsField = Annotated[
    dict[str, Any],
    Field(
        description=(
            "Black-Litterman params. Required keys: views "
            "[{pick_vector: {ticker: weight} | [floats], expected_return, "
            "confidence?}]. Optional: tau (default 0.05), risk_aversion "
            "(default 2.5), confidence_mode ('idzorek' default | "
            "'omega-direct')."
        ),
    ),
]

_ResponseFormatField = Annotated[
    ResponseFormat,
    Field(description="markdown (default) or json."),
]

_LabelField = Annotated[
    Label,
    Field(
        default=None,
        description=(
            "Optional stem for result filenames. Falls back to a hash of "
            "the inputs if unset."
        ),
    ),
]

_TotalCapitalField = Annotated[
    float | None,
    Field(default=None, description="Notional capital ($) for per-asset dollar exposure."),
]
_RiskFreeRateField = Annotated[
    float | None,
    Field(default=None, description="Risk-free rate (annualized) for Sharpe."),
]
_RiskAversionField = Annotated[
    float | None,
    Field(default=None, description="Override risk aversion λ from params."),
]
_TurnoverPenaltyField = Annotated[
    float | None,
    Field(default=None, description="L2 turnover penalty κ on |w - current_weights|²."),
]
_BudgetField = Annotated[
    float | None,
    Field(
        default=None,
        description="Sum-of-weights budget. 1.0 = fully invested; 0.0 = long/short.",
    ),
]
_ShrinkageField = Annotated[
    Shrinkage | None,
    Field(default=None, description="Covariance shrinkage (only used when --returns is set)."),
]
_ShrinkageDeltaField = Annotated[
    float | None,
    Field(default=None, description="Manual δ when shrinkage='linear'."),
]
_PeriodsPerYearField = Annotated[
    int | None,
    Field(default=None, description="Annualization factor for --returns (252 daily, 12 monthly)."),
]
_ReturnsModeField = Annotated[
    bool,
    Field(
        default=False,
        description=(
            "Interpret data as a periodic-returns CSV (rows = periods, cols = "
            "tickers) instead of an assets.json; `po` will estimate μ, Σ."
        ),
    ),
]


def _build_flags(
    total_capital: float | None,
    risk_free_rate: float | None,
    risk_aversion: float | None,
    turnover_penalty: float | None,
    budget: float | None,
    shrinkage: Shrinkage | None,
    shrinkage_delta: float | None,
    periods_per_year: int | None,
    returns_mode: bool,
) -> dict[str, Any]:
    return {
        "total_capital": total_capital,
        "risk_free_rate": risk_free_rate,
        "risk_aversion": risk_aversion,
        "turnover_penalty": turnover_penalty,
        "budget": budget,
        "shrinkage": shrinkage.value if shrinkage else None,
        "shrinkage_delta": shrinkage_delta,
        "periods_per_year": periods_per_year,
        "returns": returns_mode,
    }


def _payload(method: str, result, data_path: Path, params_path: Path | None) -> dict[str, Any]:
    return {
        "method": method,
        "weights": result.weights,
        "metrics": result.metrics,
        "diagnostics": result.diagnostics,
        "result_json_path": str(result.result_json_path),
        "argv": result.argv,
        "raw_stdout": result.raw_stdout,
        "artifacts": {
            "data": str(data_path),
            "params": str(params_path) if params_path else None,
            "result": str(result.result_json_path),
        },
    }


# ---------- registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="po_mvo",
        annotations=READ_ONLY,
        description=(
            "Single mean-variance optimal portfolio via `po mvo`. Provide "
            "either inline `data` (assets + covariance) or `data_path`. "
            "Optional `params` carry MVO constraints (bounds, budget, "
            "turnover penalty, tracking-error limit, sector group caps, "
            "etc.). With --returns and shrinkage, `data` may be a "
            "periodic-returns CSV and `po` will estimate μ and Σ. WRITES a "
            "result JSON to $PO_OUTPUT_DIR/results/."
        ),
    )
    async def po_mvo(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        total_capital: _TotalCapitalField = None,
        risk_free_rate: _RiskFreeRateField = None,
        risk_aversion: _RiskAversionField = None,
        turnover_penalty: _TurnoverPenaltyField = None,
        budget: _BudgetField = None,
        shrinkage: _ShrinkageField = None,
        shrinkage_delta: _ShrinkageDeltaField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _result_filename("mvo", label, str(data_p), str(params_p or ""))
            result = await get_runner().mvo(
                data_path=data_p,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    total_capital, risk_free_rate, risk_aversion,
                    turnover_penalty, budget, shrinkage, shrinkage_delta,
                    periods_per_year, returns_mode,
                ),
            )
            return render_small_result(
                _payload("mvo", result, data_p, params_p),
                response_format,
                title="po mvo",
                what="po_mvo",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_frontier",
        annotations=READ_ONLY,
        description=(
            "MVO efficient frontier via `po frontier`. Returns a CSV of "
            "portfolios spanning risk-aversion (or equivalently volatility) "
            "from min-variance to max-return, plus min-vol / max-Sharpe / "
            "max-return summary points. Set params.frontier_points to "
            "control density (default 50). WRITES a CSV to "
            "$PO_OUTPUT_DIR/frontiers/."
        ),
    )
    async def po_frontier(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _frontier_filename("frontier", label, str(data_p), str(params_p or ""))
            result = await get_runner().frontier(
                data_path=data_p,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            payload = {
                "method": "frontier",
                "frontier_csv_path": str(result.frontier_csv_path),
                "summary": result.summary,
                "n_points": len(result.rows),
                "rows_head": result.rows[:5],
                "rows_tail": result.rows[-5:] if len(result.rows) > 5 else [],
                "argv": result.argv,
                "raw_stdout": result.raw_stdout,
                "artifacts": {
                    "data": str(data_p),
                    "params": str(params_p) if params_p else None,
                    "frontier_csv": str(result.frontier_csv_path),
                },
            }
            return render_small_result(
                payload, response_format, title="po frontier", what="po_frontier"
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_min_variance",
        annotations=READ_ONLY,
        description=(
            "Global minimum-variance portfolio via `po min-variance`. No "
            "expected returns required. WRITES result JSON to "
            "$PO_OUTPUT_DIR/results/."
        ),
    )
    async def po_min_variance(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _result_filename(
                "min_variance", label, str(data_p), str(params_p or "")
            )
            result = await get_runner().min_variance(
                data_path=data_p,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    None, None, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            return render_small_result(
                _payload("min_variance", result, data_p, params_p),
                response_format,
                title="po min-variance",
                what="po_min_variance",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_max_sharpe",
        annotations=READ_ONLY,
        description=(
            "Maximum-Sharpe (tangency) portfolio via `po max-sharpe`. Pass "
            "risk_free_rate to anchor the Sharpe calc. WRITES a result "
            "JSON to $PO_OUTPUT_DIR/results/."
        ),
    )
    async def po_max_sharpe(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _result_filename(
                "max_sharpe", label, str(data_p), str(params_p or "")
            )
            result = await get_runner().max_sharpe(
                data_path=data_p,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            return render_small_result(
                _payload("max_sharpe", result, data_p, params_p),
                response_format,
                title="po max-sharpe",
                what="po_max_sharpe",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_target_volatility",
        annotations=READ_ONLY,
        description=(
            "Portfolio whose realized volatility ≈ target via `po target-vol "
            "--target X`. target is annualized (e.g. 0.15 = 15%). WRITES "
            "result JSON."
        ),
    )
    async def po_target_volatility(
        target_vol: Annotated[
            float,
            Field(description="Target annualized volatility, e.g. 0.15 = 15%.", gt=0.0),
        ],
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _result_filename(
                "target_vol",
                label,
                str(data_p),
                str(params_p or ""),
                f"tv{target_vol}",
            )
            result = await get_runner().target_vol(
                data_path=data_p,
                target=target_vol,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            payload = _payload("target_vol", result, data_p, params_p)
            payload["target_vol"] = target_vol
            return render_small_result(
                payload, response_format,
                title=f"po target-vol={target_vol}",
                what="po_target_volatility",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_target_return",
        annotations=READ_ONLY,
        description=(
            "Portfolio whose expected return ≈ target via `po target-return "
            "--target X`. target is annualized (e.g. 0.10 = 10%). WRITES "
            "result JSON."
        ),
    )
    async def po_target_return(
        target_return: Annotated[
            float,
            Field(description="Target annualized expected return, e.g. 0.10 = 10%."),
        ],
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="mvo")
            out = _result_filename(
                "target_return",
                label,
                str(data_p),
                str(params_p or ""),
                f"tr{target_return}",
            )
            result = await get_runner().target_return(
                data_path=data_p,
                target=target_return,
                output_path=out,
                params_path=params_p,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            payload = _payload("target_return", result, data_p, params_p)
            payload["target_return"] = target_return
            return render_small_result(
                payload, response_format,
                title=f"po target-return={target_return}",
                what="po_target_return",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_black_litterman",
        annotations=READ_ONLY,
        description=(
            "Black-Litterman single optimal portfolio via `po bl`. Requires "
            "`params` with at least one view: "
            "{views: [{pick_vector: {ticker: weight}, expected_return, "
            "confidence}], tau, risk_aversion, confidence_mode}. "
            "show_model=True surfaces prior vs posterior return diagnostics. "
            "WRITES result JSON."
        ),
    )
    async def po_black_litterman(
        params: _BLParamsField,
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: _LabelField = None,
        show_model: Annotated[
            bool,
            Field(default=False, description="Print BL model diagnostics."),
        ] = False,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="bl")
            if params_p is None:
                raise POError("Black-Litterman requires non-empty `params` with views.")
            out = _result_filename("bl", label, str(data_p), str(params_p))
            result = await get_runner().bl(
                data_path=data_p,
                params_path=params_p,
                output_path=out,
                show_model=show_model,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            return render_small_result(
                _payload("bl", result, data_p, params_p),
                response_format,
                title="po bl",
                what="po_black_litterman",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_bl_frontier",
        annotations=READ_ONLY,
        description=(
            "Black-Litterman efficient frontier via `po bl-frontier`. Same "
            "view structure as po_black_litterman. WRITES a CSV to "
            "$PO_OUTPUT_DIR/frontiers/."
        ),
    )
    async def po_bl_frontier(
        params: _BLParamsField,
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: _LabelField = None,
        risk_free_rate: _RiskFreeRateField = None,
        shrinkage: _ShrinkageField = None,
        periods_per_year: _PeriodsPerYearField = None,
        returns_mode: _ReturnsModeField = False,
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = _resolve_params_input(params, kind="bl")
            if params_p is None:
                raise POError("BL frontier requires non-empty `params` with views.")
            out = _frontier_filename("bl_frontier", label, str(data_p), str(params_p))
            result = await get_runner().bl_frontier(
                data_path=data_p,
                params_path=params_p,
                output_path=out,
                **_build_flags(
                    None, risk_free_rate, None, None, None,
                    shrinkage, None, periods_per_year, returns_mode,
                ),
            )
            payload = {
                "method": "bl_frontier",
                "frontier_csv_path": str(result.frontier_csv_path),
                "summary": result.summary,
                "n_points": len(result.rows),
                "rows_head": result.rows[:5],
                "rows_tail": result.rows[-5:] if len(result.rows) > 5 else [],
                "argv": result.argv,
                "raw_stdout": result.raw_stdout,
                "artifacts": {
                    "data": str(data_p),
                    "params": str(params_p),
                    "frontier_csv": str(result.frontier_csv_path),
                },
            }
            return render_small_result(
                payload, response_format, title="po bl-frontier",
                what="po_bl_frontier",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_report",
        annotations=READ_ONLY,
        description=(
            "Generate a Jupyter diagnostic report (HTML + executed notebook) "
            "via `po report`. method='mvo' runs only MVO; 'bl' runs only "
            "Black-Litterman; 'both' (default) runs both side-by-side. "
            "WRITES to $PO_OUTPUT_DIR/reports/<label>/."
        ),
    )
    async def po_report(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        params: _ParamsField = None,
        label: _LabelField = None,
        method: Annotated[
            Literal["mvo", "bl", "both"],
            Field(description="Which methods to run in the report."),
        ] = "both",
        response_format: _ResponseFormatField = ResponseFormat.markdown,
    ) -> str:
        try:
            data_p = _resolve_data_input(data, data_path)
            params_p = (
                _resolve_params_input(params, kind="bl" if method == "bl" else "mvo")
                if params
                else None
            )
            stem = label_or_hash(label, "report", str(data_p), method)
            out_dir = reports_dir() / stem
            result = await get_runner().report(
                data_path=data_p,
                output_dir=out_dir,
                params_path=params_p,
                method=method,
            )
            payload = {
                "method": "report",
                "output_dir": str(result.output_dir),
                "html_path": str(result.html_path) if result.html_path else None,
                "notebook_path": (
                    str(result.notebook_path) if result.notebook_path else None
                ),
                "argv": result.argv,
                "raw_stdout": result.raw_stdout,
                "artifacts": {
                    "data": str(data_p),
                    "params": str(params_p) if params_p else None,
                    "html": str(result.html_path) if result.html_path else None,
                    "notebook": (
                        str(result.notebook_path) if result.notebook_path else None
                    ),
                },
            }
            return render_small_result(
                payload, response_format, title=f"po report ({method})",
                what="po_report",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
