"""Data preparation tools.

Two tools turn sibling-connector output into the single-column CSV that
``ag fit`` expects:

- ``ag_prepare_returns`` — convert an existing prices CSV (e.g. one
  written to ``$FMP_OUTPUT_DIR``) into log/simple returns.
- ``ag_load_series`` — direct-from-source convenience: call FMP/BLS/BEA
  itself, persist the raw series under ``$AG_OUTPUT_DIR``, and return
  the returns CSV path. Reuses the sibling connectors' env vars
  (`FMP_API_KEY`, `BLS_API_KEY`, `BEA_API_KEY`) so a single-tool
  workflow is possible when all the caller needs is the price series.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from turningbull_mcp.config import require_env
from turningbull_mcp.http import make_async_client

from ..errors import AGError
from ..models import (
    OptionalDate,
    ResponseFormat,
    ReturnType,
)
from ..output import prices_dir, returns_dir, safe_filename, series_dir
from ..preprocessing import (
    ReturnsMetadata,
    prices_to_returns,
    series_to_returns,
    write_series_csv,
)
from ._common import READ_ONLY, render_small_result, wrap_error

# ---------- HTTP helpers (FMP/BLS/BEA fetchers) --------------------------

FMP_BASE_URL = "https://financialmodelingprep.com"
BLS_V2_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BEA_BASE_URL = "https://apps.bea.gov/api/data"


async def _fetch_fmp_prices(
    symbol: str,
    *,
    from_date: str | None,
    to_date: str | None,
) -> list[dict[str, Any]]:
    """GET FMP historical EOD prices for a single symbol.

    Reuses the same env var (``FMP_API_KEY``) and endpoint that
    ``fmp_mcp`` uses, but issues its own HTTP call so this tool doesn't
    require the FMP server to be running.
    """
    api_key = require_env(
        "FMP_API_KEY",
        hint="Set FMP_API_KEY in your .env to use source='fmp_prices'.",
    )
    params: dict[str, Any] = {"symbol": symbol, "apikey": api_key}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    async with make_async_client(user_agent="ag-mcp/0.1") as http:
        resp = await http.get(
            f"{FMP_BASE_URL}/stable/historical-price-eod/full", params=params
        )
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("historical"), list):
        return data["historical"]
    return []


async def _fetch_bls_series(
    series_id: str,
    *,
    from_date: str | None,
    to_date: str | None,
    extras: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Single-series BLS fetch returning ``[{date, value, period}, ...]``.

    Uses v2 when ``BLS_API_KEY`` is set, falls back to v1 otherwise.
    """
    import os

    api_key = os.environ.get("BLS_API_KEY", "").strip()
    start_year = from_date[:4] if from_date else None
    end_year = to_date[:4] if to_date else None
    async with make_async_client(user_agent="ag-mcp/0.1") as http:
        if api_key:
            body: dict[str, Any] = {
                "seriesid": [series_id],
                "registrationkey": api_key,
            }
            if start_year:
                body["startyear"] = start_year
            if end_year:
                body["endyear"] = end_year
            if extras:
                body.update(extras)
            resp = await http.post(BLS_V2_URL, json=body)
        else:
            params: dict[str, Any] = {}
            if start_year:
                params["startyear"] = start_year
            if end_year:
                params["endyear"] = end_year
            resp = await http.get(f"{BLS_V1_URL}{series_id}", params=params or None)
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("status") != "REQUEST_SUCCEEDED":
        msgs = payload.get("message") or []
        raise AGError(
            "BLS API rejected the request: "
            + "; ".join(str(m) for m in msgs)
        )
    series = (payload.get("Results") or {}).get("series") or []
    if not series:
        return []
    raw = series[0].get("data") or []
    rows: list[dict[str, Any]] = []
    for obs in raw:
        try:
            val = float(obs.get("value"))
        except (TypeError, ValueError):
            continue
        year = obs.get("year")
        period = obs.get("period") or ""
        date = _bls_iso_date(year, period)
        if date is None:
            continue
        rows.append({"date": date, "value": val, "period": period})
    rows.sort(key=lambda r: r["date"])
    return rows


def _bls_iso_date(year: Any, period: str) -> str | None:
    """Convert a (year, period) pair into ISO date. Tolerates unknowns."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    p = (period or "").strip().upper()
    if not p:
        return None
    code = p[:1]
    try:
        n = int(p[1:])
    except ValueError:
        return None
    if code == "M":
        if n == 13:
            return f"{y:04d}-12-31"
        if 1 <= n <= 12:
            return f"{y:04d}-{n:02d}-01"
    if code == "Q" and 1 <= n <= 4:
        m = (n - 1) * 3 + 1
        return f"{y:04d}-{m:02d}-01"
    if code == "S":
        if n == 1:
            return f"{y:04d}-01-01"
        if n == 2:
            return f"{y:04d}-07-01"
    if code == "A":
        return f"{y:04d}-01-01"
    return None


async def _fetch_bea_series(
    identifier: str,
    *,
    from_date: str | None,
    to_date: str | None,
    extras: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """BEA fetch. ``identifier`` is a dataset-qualified token; ``extras`` carries
    the dataset-specific parameters (TableName, LineCode, GeoFips, …)."""
    api_key = require_env(
        "BEA_API_KEY",
        hint="Set BEA_API_KEY in your .env to use source='bea_series'.",
    )
    if not extras:
        raise AGError(
            "source='bea_series' requires `extras` with at least dataset/"
            "TableName/LineCode/Frequency (and GeoFips for regional). See "
            "BEA_ENDPOINTS.md for dataset-specific parameters."
        )
    dataset = extras.get("dataset") or extras.get("DataSetName")
    if not dataset:
        raise AGError("extras['dataset'] is required for source='bea_series'.")
    params: dict[str, Any] = {
        "UserID": api_key,
        "method": "GetData",
        "DataSetName": dataset,
        "ResultFormat": "JSON",
    }
    # Compose Year window from from/to dates if not provided in extras.
    if "Year" not in extras and (from_date or to_date):
        years: list[str] = []
        if from_date and to_date:
            sy, ey = int(from_date[:4]), int(to_date[:4])
            years = [str(y) for y in range(sy, ey + 1)]
        elif from_date:
            years = [from_date[:4]]
        elif to_date:
            years = [to_date[:4]]
        if years:
            params["Year"] = ",".join(years)
    for k, v in extras.items():
        if k.lower() == "dataset" or v is None:
            continue
        params[k] = v
    async with make_async_client(user_agent="ag-mcp/0.1") as http:
        resp = await http.get(BEA_BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    envelope = (payload or {}).get("BEAAPI") or {}
    results = envelope.get("Results") or {}
    if isinstance(results, dict) and results.get("Error"):
        err = results["Error"]
        raise AGError(f"BEA API error: {err}")
    data = (results or {}).get("Data") or []
    rows: list[dict[str, Any]] = []
    for entry in data:
        raw_val = entry.get("DataValue")
        if raw_val is None:
            continue
        try:
            val = float(str(raw_val).replace(",", ""))
        except (TypeError, ValueError):
            continue
        time_period = str(entry.get("TimePeriod") or "")
        iso = _bea_iso_date(time_period)
        if iso is None:
            continue
        rows.append({"date": iso, "value": val, "time_period": time_period})
    # Optional: filter to caller-supplied date window.
    if from_date:
        rows = [r for r in rows if r["date"] >= from_date]
    if to_date:
        rows = [r for r in rows if r["date"] <= to_date]
    rows.sort(key=lambda r: r["date"])
    if not rows:
        raise AGError(
            "BEA returned no data rows for the given parameters. Verify "
            "the dataset/TableName/LineCode combination via the BEA discovery tools."
        )
    return rows


def _bea_iso_date(time_period: str) -> str | None:
    """Convert a BEA TimePeriod string like ``2024Q3`` / ``2024M07`` / ``2024``."""
    s = time_period.strip().upper()
    if not s:
        return None
    if len(s) == 4 and s.isdigit():
        return f"{int(s):04d}-01-01"
    if "Q" in s:
        try:
            y, q = s.split("Q")
            yi, qi = int(y), int(q)
            if 1 <= qi <= 4:
                return f"{yi:04d}-{(qi - 1) * 3 + 1:02d}-01"
        except ValueError:
            return None
    if "M" in s:
        try:
            y, m = s.split("M")
            yi, mi = int(y), int(m)
            if 1 <= mi <= 12:
                return f"{yi:04d}-{mi:02d}-01"
        except ValueError:
            return None
    return None


# ---------- registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="ag_prepare_returns",
        annotations=READ_ONLY,
        description=(
            "Convert an existing prices CSV into a returns CSV usable as "
            "input to ag_fit/ag_select. Defaults to log returns "
            "(ln(p_t/p_{t-1})), which is the analytical default for GARCH "
            "modelling. Pass return_type='simple' for arithmetic returns "
            "or 'none' if the input series is already stationary (e.g. a "
            "YoY % change). The CSV must have a price column "
            "(adjClose/close/price) and optionally a date column for "
            "sorting. Output is a single-column CSV under "
            "$AG_OUTPUT_DIR/returns/."
        ),
    )
    async def ag_prepare_returns(
        prices_csv_path: Annotated[
            str,
            Field(description="Path to a CSV with price+date columns (e.g. an FMP_OUTPUT_DIR file)."),
        ],
        symbol_or_label: Annotated[
            str,
            Field(description="Used as filename stem for the output CSV."),
        ],
        return_type: Annotated[
            ReturnType,
            Field(description="log (default), simple, or none."),
        ] = ReturnType.log,
        price_column: Annotated[
            str,
            Field(description="Column name to use as price (default adjClose)."),
        ] = "adjClose",
        date_column: Annotated[
            str | None,
            Field(description="Date column for chronological sort. Pass null to skip."),
        ] = "date",
        annualization_factor: Annotated[
            int | None,
            Field(description="Steps per year (auto-inferred if unset)."),
        ] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            in_path = Path(prices_csv_path).expanduser()
            if not in_path.exists():
                raise AGError(f"prices CSV not found: {in_path}")
            stem = safe_filename(symbol_or_label) or "series"
            out_path = returns_dir() / f"{stem}_{return_type.value}_returns.csv"
            meta = prices_to_returns(
                in_path,
                output_csv=out_path,
                return_type=return_type.value,
                price_column=price_column,
                date_column=date_column,
                annualization_factor=annualization_factor,
            )
            return render_small_result(
                meta.to_dict(),
                response_format,
                title=f"Returns prepared for {symbol_or_label}",
                what="ag_prepare_returns",
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)

    @mcp.tool(
        name="ag_load_series",
        annotations=READ_ONLY,
        description=(
            "Direct-from-source convenience: fetch a price/series from "
            "FMP/BLS/BEA, persist the raw data under $AG_OUTPUT_DIR, and "
            "derive a returns CSV in one call. source='fmp_prices' uses "
            "FMP historical EOD (identifier=symbol, default return_type=log); "
            "source='bls_series' (identifier=series_id, default return_type=none) "
            "and source='bea_series' (identifier=label; pass extras={dataset, "
            "TableName, LineCode, Frequency, GeoFips, ...}) are also supported. "
            "Reuses the sibling connectors' env vars (FMP_API_KEY/BLS_API_KEY/"
            "BEA_API_KEY). Returns the returns CSV path plus a summary."
        ),
    )
    async def ag_load_series(
        source: Annotated[
            Literal["fmp_prices", "bls_series", "bea_series"],
            Field(description="fmp_prices | bls_series | bea_series."),
        ],
        identifier: Annotated[
            str,
            Field(description="Symbol (FMP), series_id (BLS), or label (BEA)."),
        ],
        from_date: OptionalDate = None,
        to_date: OptionalDate = None,
        return_type: Annotated[
            ReturnType | None,
            Field(
                description=(
                    "Override the source-specific default: log for fmp_prices, "
                    "none for bls_series/bea_series."
                ),
            ),
        ] = None,
        price_column: Annotated[
            str,
            Field(description="FMP price column (default adjClose)."),
        ] = "adjClose",
        extras: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Source-specific extras. For bea_series this MUST include "
                    "'dataset' plus TableName/LineCode/Frequency/GeoFips as needed."
                ),
            ),
        ] = None,
        annualization_factor: Annotated[
            int | None,
            Field(description="Steps per year override (auto-inferred if unset)."),
        ] = None,
        response_format: Annotated[
            ResponseFormat, Field(description="markdown or json.")
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            meta = await _load_series_impl(
                source=source,
                identifier=identifier,
                from_date=from_date,
                to_date=to_date,
                return_type=return_type,
                price_column=price_column,
                extras=extras,
                annualization_factor=annualization_factor,
            )
            return render_small_result(
                meta.to_dict(),
                response_format,
                title=f"{source}: {identifier}",
                what="ag_load_series",
            )
        except httpx.HTTPStatusError as exc:
            return wrap_error(
                AGError(f"upstream {source} HTTP error {exc.response.status_code}: {exc!s}")
            )
        except Exception as exc:  # noqa: BLE001
            return wrap_error(exc)


# ---------- implementation that composites can call --------------------


async def _load_series_impl(
    *,
    source: Literal["fmp_prices", "bls_series", "bea_series"],
    identifier: str,
    from_date: str | None,
    to_date: str | None,
    return_type: ReturnType | None,
    price_column: str = "adjClose",
    extras: dict[str, Any] | None = None,
    annualization_factor: int | None = None,
) -> ReturnsMetadata:
    """Source dispatch shared by ``ag_load_series`` and the composite tools."""
    safe_id = safe_filename(identifier)

    if source == "fmp_prices":
        rows = await _fetch_fmp_prices(
            identifier.upper(), from_date=from_date, to_date=to_date
        )
        if not rows:
            raise AGError(
                f"FMP returned no historical-EOD rows for {identifier!r} "
                "in the requested window."
            )
        prices_csv = prices_dir() / f"{safe_id}_prices.csv"
        import pandas as pd

        df = pd.DataFrame(rows)
        df.to_csv(prices_csv, index=False)
        rt = (return_type or ReturnType.log).value
        out_csv = returns_dir() / f"{safe_id}_{rt}_returns.csv"
        # Pick a price column the file actually has.
        col = price_column if price_column in df.columns else _fmp_default_price_column(df)
        return prices_to_returns(
            prices_csv,
            output_csv=out_csv,
            return_type=rt,  # type: ignore[arg-type]
            price_column=col,
            date_column="date" if "date" in df.columns else None,
            annualization_factor=annualization_factor,
        )

    if source == "bls_series":
        rows = await _fetch_bls_series(
            identifier.upper(),
            from_date=from_date,
            to_date=to_date,
            extras=extras,
        )
        if not rows:
            raise AGError(
                f"BLS returned no observations for {identifier!r} "
                "in the requested window."
            )
        series_csv = series_dir() / f"{safe_id}_series.csv"
        write_series_csv(rows, series_csv, value_key="value")
        rt = (return_type or ReturnType.none).value
        out_csv = returns_dir() / f"{safe_id}_{rt}_returns.csv"
        return series_to_returns(
            rows,
            output_csv=out_csv,
            return_type=rt,  # type: ignore[arg-type]
            value_key="value",
            date_key="date",
            annualization_factor=annualization_factor,
        )

    if source == "bea_series":
        rows = await _fetch_bea_series(
            identifier,
            from_date=from_date,
            to_date=to_date,
            extras=extras,
        )
        series_csv = series_dir() / f"{safe_id}_series.csv"
        write_series_csv(rows, series_csv, value_key="value")
        rt = (return_type or ReturnType.none).value
        out_csv = returns_dir() / f"{safe_id}_{rt}_returns.csv"
        return series_to_returns(
            rows,
            output_csv=out_csv,
            return_type=rt,  # type: ignore[arg-type]
            value_key="value",
            date_key="date",
            annualization_factor=annualization_factor,
        )

    raise AGError(f"unknown source {source!r}")


def _fmp_default_price_column(df: Any) -> str:
    """Pick a price column FMP actually returned for this row set."""
    for c in ("adjClose", "close", "Close", "price"):
        if c in df.columns:
            return c
    raise AGError(
        "FMP response had no recognizable price column "
        "(adjClose/close/price)."
    )
