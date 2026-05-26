"""Closed-form portfolio constructions backed by :mod:`portopt`.

These tools wrap functions only exposed by the `portopt` Python library
(HRP, ERC, inverse-var/vol, equal-weight, max-diversification). Each
imports `portopt` lazily via :mod:`po_mcp.pyengine`, so a CLI-only
install still loads the connector — these tools error with an actionable
message if the user calls them without `portopt` available.

Every tool returns a flat payload with ``weights``, ``metrics`` (vol,
diversification ratio, effective N, gross exposure), and per-asset
``risk_contributions``. Results are persisted to
``$PO_OUTPUT_DIR/results/<method>_<hash>.json`` so they're indexable by
``po_list_results``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import pyengine
from ..errors import POError
from ..models import (
    AssetDataInline,
    DataPathInput,
    Label,
    ResponseFormat,
    materialize_data,
)
from ..output import content_hash, label_or_hash, results_dir
from ._common import READ_ONLY, render_small_result, wrap_error


_DataInlineField = Annotated[
    dict[str, Any] | None,
    Field(
        default=None,
        description=(
            "Inline assets payload (requires `covariance` at minimum; "
            "asset tickers default to `assets[].ticker`). Provide either "
            "this or `data_path`."
        ),
    ),
]
_DataPathField = Annotated[
    str | None,
    Field(
        default=None,
        description="Path to an assets.json file on disk.",
    ),
]


def _load_assets(
    data: dict[str, Any] | None, data_path: str | None
) -> tuple[list[str], list[list[float]]]:
    """Resolve and parse an assets.json (inline or on-disk) into
    ``(tickers, covariance)``.
    """
    if (data is None) == (data_path is None):
        raise POError(
            "Provide exactly one of `data` (inline assets JSON) or `data_path`."
        )
    if data is not None:
        validated = AssetDataInline.model_validate(
            {**{k: v for k, v in data.items() if k != "kind"}, "kind": "inline"}
        )
        materialize_data(validated)  # also cache to tmp/ for downstream tools
        tickers = [a.ticker for a in validated.assets]
        covariance = validated.covariance
    else:
        path = Path(data_path)  # type: ignore[arg-type]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise POError(f"could not read assets file {path}: {exc}") from exc
        tickers = [a.get("ticker", f"asset_{i}") for i, a in enumerate(payload.get("assets", []))]
        covariance = payload.get("covariance") or []
        materialize_data(DataPathInput(path=path))
    if not tickers or not covariance:
        raise POError(
            "Inputs missing `assets[].ticker` or `covariance` — these are required "
            "for closed-form portfolio constructions."
        )
    if len(covariance) != len(tickers) or any(len(row) != len(tickers) for row in covariance):
        raise POError(
            f"covariance shape mismatch: {len(covariance)}x... vs {len(tickers)} tickers."
        )
    return tickers, covariance


def _persist_result(method: str, label: str | None, payload: dict[str, Any]) -> Path:
    stem = label_or_hash(label, method, content_hash(json.dumps(payload, sort_keys=True, default=str)))
    path = results_dir() / f"{method}_{stem}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="po_equal_risk_contribution",
        annotations=READ_ONLY,
        description=(
            "Equal-risk-contribution (ERC, risk-parity) weights using "
            "portopt.portfolios.equal_risk_contribution. Returns weights, "
            "per-asset risk contributions, portfolio volatility, "
            "diversification ratio, effective N. Long-only, budget=1, no "
            "expected returns required. Requires `portopt`."
        ),
    )
    async def po_equal_risk_contribution(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        tolerance: Annotated[
            float, Field(default=1e-8, description="ERC tolerance.", gt=0.0)
        ] = 1e-8,
        max_iters: Annotated[
            int, Field(default=5000, description="ERC max iterations.", ge=100)
        ] = 5000,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, cov = _load_assets(data, data_path)
            result = pyengine.equal_risk_contribution(
                tickers, cov, tolerance=tolerance, max_iters=max_iters
            )
            result["method"] = "risk_parity"
            path = _persist_result("risk_parity", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po risk parity (ERC)",
                what="po_equal_risk_contribution",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_hierarchical_risk_parity",
        annotations=READ_ONLY,
        description=(
            "Hierarchical Risk Parity (López de Prado 2016) via "
            "portopt.portfolios.hierarchical_risk_parity. Clustering-based; "
            "robust to ill-conditioned Σ. Long-only, budget=1. "
            "Requires `portopt`."
        ),
    )
    async def po_hierarchical_risk_parity(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, cov = _load_assets(data, data_path)
            result = pyengine.hierarchical_risk_parity(tickers, cov)
            result["method"] = "hrp"
            path = _persist_result("hrp", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po HRP",
                what="po_hierarchical_risk_parity",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_inverse_variance",
        annotations=READ_ONLY,
        description=(
            "Inverse-variance weights: w_i ∝ 1/σ_i². Long-only, budget=1. "
            "Requires `portopt`."
        ),
    )
    async def po_inverse_variance(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, cov = _load_assets(data, data_path)
            result = pyengine.inverse_variance(tickers, cov)
            result["method"] = "inverse_variance"
            path = _persist_result("inverse_variance", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po inverse-variance",
                what="po_inverse_variance",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_inverse_volatility",
        annotations=READ_ONLY,
        description=(
            "Inverse-volatility weights: w_i ∝ 1/σ_i. Long-only, budget=1. "
            "Requires `portopt`."
        ),
    )
    async def po_inverse_volatility(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, cov = _load_assets(data, data_path)
            result = pyengine.inverse_volatility(tickers, cov)
            result["method"] = "inverse_volatility"
            path = _persist_result("inverse_volatility", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po inverse-volatility",
                what="po_inverse_volatility",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_equal_weight",
        annotations=READ_ONLY,
        description=(
            "1/N portfolio across the supplied tickers. Pure-Python (no "
            "`portopt` import); useful as a benchmark and for "
            "po_compare_methods. Either provide `tickers` directly or "
            "supply inline `data` / `data_path` to read tickers from an "
            "assets.json."
        ),
    )
    async def po_equal_weight(
        tickers: Annotated[
            list[str] | None,
            Field(default=None, description="Asset tickers; if omitted, read from `data`/`data_path`."),
        ] = None,
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if tickers is None:
                tickers, _ = _load_assets(data, data_path)
            result = pyengine.equal_weight(list(tickers))
            result["method"] = "equal_weight"
            path = _persist_result("equal_weight", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po equal-weight (1/N)",
                what="po_equal_weight",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="po_max_diversification",
        annotations=READ_ONLY,
        description=(
            "Maximum-diversification portfolio (Choueifaty & Coignard 2008) "
            "via portopt.portfolios.maximum_diversification — maximizes "
            "(w·σ) / σ_port. Long-only, budget=1. Requires `portopt`."
        ),
    )
    async def po_max_diversification(
        data: _DataInlineField = None,
        data_path: _DataPathField = None,
        label: Annotated[Label, Field(default=None, description="Optional filename stem.")] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            tickers, cov = _load_assets(data, data_path)
            result = pyengine.max_diversification(tickers, cov)
            result["method"] = "max_diversification"
            path = _persist_result("max_diversification", label, result)
            result["result_json_path"] = str(path)
            return render_small_result(
                result, response_format, title="po max-diversification",
                what="po_max_diversification",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)
