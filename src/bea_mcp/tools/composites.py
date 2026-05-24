"""Curated composite BEA dashboards.

Four opinionated snapshots tailored to common macro questions. Each tool
makes 1-3 BEA calls and assembles a structured dict that's easy for a
model to narrate. Heavy lifting (period parsing, value coercion) is in
``transform.py``; pivoting/percent change uses pandas in-process.
"""

from __future__ import annotations

from typing import Annotated, Any

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import get_client
from ..models import ResponseFormat
from ..transform import flatten_data
from ._common import READ_ONLY, render_small_result, wrap_error


def _series_payload(
    name: str,
    series_code: str,
    series_rows: list[dict[str, Any]],
    history_n: int,
) -> dict[str, Any]:
    """Reshape one component's rows into a {latest, yoy, history} block."""
    rows = sorted(
        (r for r in series_rows if r.get("date") and r.get("value") is not None),
        key=lambda r: r["date"],
    )
    if not rows:
        return {
            "name": name,
            "series_code": series_code,
            "latest_date": None,
            "latest_value": None,
            "yoy_pct": None,
            "history": [],
        }
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    df["yoy_pct"] = df["value"].pct_change(periods=12).mul(100.0).fillna(
        df["value"].pct_change(periods=4).mul(100.0)
    )
    tail = df.tail(history_n)
    latest = df.iloc[-1]
    return {
        "name": name,
        "series_code": series_code,
        "latest_date": str(latest["date"].date()),
        "latest_value": float(latest["value"]),
        "yoy_pct": (
            float(latest["yoy_pct"])
            if pd.notna(latest.get("yoy_pct"))
            else None
        ),
        "history": [
            {
                "date": str(r["date"].date()),
                "value": float(r["value"]),
                "yoy_pct": (
                    float(r["yoy_pct"]) if pd.notna(r.get("yoy_pct")) else None
                ),
            }
            for _, r in tail.iterrows()
        ],
    }


def _group_by_series(rows: list[dict[str, Any]], key: str = "SeriesCode") -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        k = r.get(key)
        if k is None:
            continue
        out.setdefault(str(k), []).append(r)
    return out


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bea_gdp_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call US GDP dashboard. Pulls NIPA T10101 (% change in real "
            "GDP) and T10102 (contributions to % change), quarterly. "
            "Returns a structured payload with headline real GDP growth, "
            "the contributions from PCE / Gross Private Domestic Investment "
            "/ Net Exports / Government, and a history window. Use this for "
            "'what's the latest GDP print?' and 'what drove growth?'."
        ),
    )
    async def bea_gdp_snapshot(
        quarters_back: Annotated[
            int,
            Field(default=8, ge=1, le=80, description="Length of history window."),
        ] = 8,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            growth_results = await client.call(
                "GetData",
                dataset="NIPA",
                params={"TableName": "T10101", "Frequency": "Q", "Year": "LAST10"},
            )
            contrib_results = await client.call(
                "GetData",
                dataset="NIPA",
                params={"TableName": "T10102", "Frequency": "Q", "Year": "LAST10"},
            )
            growth_rows = flatten_data(growth_results.get("Data") or [])
            contrib_rows = flatten_data(contrib_results.get("Data") or [])

            growth_by_series = _group_by_series(growth_rows)
            contrib_by_series = _group_by_series(contrib_rows)

            # Find the headline GDP line (LineNumber 1 in T10101) and the
            # major component contributions (LineNumber 1=GDP, 2=PCE,
            # 8=GPDI, 14=NetExports, 22=Government in T10102).
            def _first_for_line(by_series: dict[str, list[dict]], line: str) -> tuple[str, list[dict]]:
                for code, items in by_series.items():
                    if items and str(items[0].get("LineNumber")) == line:
                        return code, items
                return "", []

            payload: dict[str, Any] = {"components": {}}
            gdp_code, gdp_rows = _first_for_line(growth_by_series, "1")
            if gdp_rows:
                payload["headline_real_gdp_growth_pct"] = _series_payload(
                    "real_gdp_pct_change_saar",
                    gdp_code or "T10101_L1",
                    gdp_rows,
                    quarters_back,
                )
                payload["as_of"] = payload["headline_real_gdp_growth_pct"]["latest_date"]

            component_lines = {
                "personal_consumption": "2",
                "gross_private_domestic_investment": "8",
                "net_exports": "14",
                "government": "22",
            }
            for name, line in component_lines.items():
                code, rows = _first_for_line(contrib_by_series, line)
                if rows:
                    payload["components"][name] = _series_payload(
                        f"contribution_{name}",
                        code or f"T10102_L{line}",
                        rows,
                        quarters_back,
                    )

            return render_small_result(
                payload,
                response_format,
                title="BEA GDP snapshot",
                what="GDP snapshot",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_trade_balance_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call US current-account / trade-balance dashboard. Pulls "
            "ITA balances for current account, goods, services, and "
            "secondary income at annual frequency, plus IIP net "
            "international investment position. Returns latest values, YoY "
            "change, and a multi-year history."
        ),
    )
    async def bea_trade_balance_snapshot(
        years_back: Annotated[
            int,
            Field(default=5, ge=1, le=40, description="Length of history window (years)."),
        ] = 5,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            indicators = [
                ("current_account_balance", "BalCurrAcct"),
                ("goods_balance", "BalGds"),
                ("services_balance", "BalServ"),
                ("goods_and_services_balance", "BalGdsServ"),
                ("secondary_income_balance", "BalSecondaryInc"),
            ]
            ita_results = await client.call(
                "GetData",
                dataset="ITA",
                params={
                    "Indicator": ",".join(ind for _, ind in indicators),
                    "AreaOrCountry": "AllCountries",
                    "Frequency": "A",
                    "Year": "ALL",
                },
            )
            ita_rows = flatten_data(ita_results.get("Data") or [])

            payload: dict[str, Any] = {"components": {}}
            for label, indicator in indicators:
                rows = [r for r in ita_rows if r.get("Indicator") == indicator]
                if rows:
                    payload["components"][label] = _series_payload(
                        label, indicator, rows, years_back
                    )

            try:
                iip_results = await client.call(
                    "GetData",
                    dataset="IIP",
                    params={
                        "TypeOfInvestment": "FinAssetsExclFinDeriv",
                        "Component": "ChgPosTotal",
                        "Frequency": "A",
                        "Year": "ALL",
                    },
                )
                iip_rows = flatten_data(iip_results.get("Data") or [])
                if iip_rows:
                    payload["components"]["iip_change_position"] = _series_payload(
                        "iip_change_position",
                        "FinAssetsExclFinDeriv",
                        iip_rows,
                        years_back,
                    )
            except Exception:
                # IIP call is best-effort; the trade balance dashboard is
                # still useful without it.
                pass

            if "current_account_balance" in payload["components"]:
                payload["as_of"] = payload["components"]["current_account_balance"][
                    "latest_date"
                ]
            return render_small_result(
                payload,
                response_format,
                title="BEA trade balance snapshot",
                what="trade balance",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_regional_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call US regional snapshot. Pulls Regional SAGDP9N (real "
            "GDP by state, chained dollars) for all states or a specific "
            "FIPS code. Returns latest level, prior-year level, and "
            "year-over-year growth for each state. Use geo_fips='STATE' "
            "for all 50 states + DC; pass a 5-digit FIPS (e.g. '06000') "
            "for a single state."
        ),
    )
    async def bea_regional_snapshot(
        geo_fips: Annotated[
            str,
            Field(
                default="STATE",
                description="STATE (default), COUNTY, MSA, or a 5-digit FIPS code.",
            ),
        ] = "STATE",
        years_back: Annotated[
            int,
            Field(default=5, ge=1, le=30, description="Length of history window (years)."),
        ] = 5,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            # SAGDP9N LineCode=1 → "All industry total" real GDP.
            results = await client.call(
                "GetData",
                dataset="Regional",
                params={
                    "TableName": "SAGDP9N",
                    "LineCode": 1,
                    "GeoFips": geo_fips,
                    "Year": f"LAST{max(years_back + 1, 5)}",
                },
            )
            rows = flatten_data(results.get("Data") or [])
            # Group by GeoFips and compute latest + YoY.
            by_geo: dict[str, list[dict]] = {}
            for r in rows:
                gf = str(r.get("GeoFips") or "")
                if gf:
                    by_geo.setdefault(gf, []).append(r)

            snapshots: list[dict[str, Any]] = []
            latest_date_global = ""
            for gf, items in by_geo.items():
                items = sorted(
                    (i for i in items if i.get("date") and i.get("value") is not None),
                    key=lambda r: r["date"],
                )
                if not items:
                    continue
                latest = items[-1]
                prior = items[-2] if len(items) >= 2 else None
                yoy = None
                if prior and prior["value"]:
                    yoy = (latest["value"] / prior["value"] - 1.0) * 100.0
                latest_date_global = max(latest_date_global, str(latest["date"]))
                snapshots.append(
                    {
                        "geo_fips": gf,
                        "geo_name": latest.get("GeoName"),
                        "latest_date": latest["date"],
                        "latest_value": latest["value"],
                        "prior_value": prior["value"] if prior else None,
                        "yoy_pct": yoy,
                    }
                )
            snapshots.sort(
                key=lambda r: (r["yoy_pct"] is None, -(r["yoy_pct"] or 0.0))
            )
            payload = {
                "as_of": latest_date_global or None,
                "table": "SAGDP9N (Real GDP by state, chained dollars)",
                "geo_fips": geo_fips,
                "rows": snapshots,
            }
            return render_small_result(
                payload,
                response_format,
                title=f"BEA regional snapshot ({geo_fips})",
                what="regional GDP",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bea_personal_income_snapshot",
        annotations=READ_ONLY,
        description=(
            "One-call US personal income dashboard. Pulls NIPA T20600 "
            "(monthly personal income and its disposition). Returns "
            "personal income, disposable personal income, personal savings "
            "rate, and real PCE — each with latest value, YoY change, and "
            "a history window. Use this for 'how are households doing?'."
        ),
    )
    async def bea_personal_income_snapshot(
        months_back: Annotated[
            int,
            Field(default=24, ge=1, le=240, description="Length of history window (months)."),
        ] = 24,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            client = get_client()
            results = await client.call(
                "GetData",
                dataset="NIPA",
                params={
                    "TableName": "T20600",
                    "Frequency": "M",
                    "Year": "LAST10",
                },
            )
            rows = flatten_data(results.get("Data") or [])
            by_line = _group_by_series(rows, key="LineNumber")

            # T20600 LineNumbers (standard layout):
            # 1=Personal income, 27=Disposable personal income,
            # 35=Personal saving as a percentage of DPI,
            # … real PCE is on a different table; we approximate with
            # nominal PCE (LineNumber 22) for the household view.
            components = {
                "personal_income": "1",
                "disposable_personal_income": "27",
                "personal_outlays": "22",
                "personal_saving_rate_pct": "35",
            }
            payload: dict[str, Any] = {"components": {}}
            latest_date_global = ""
            for label, line in components.items():
                line_rows = by_line.get(str(line)) or []
                if not line_rows:
                    continue
                # Some lines repeat across SeriesCodes (different units);
                # pick the SeriesCode with the most observations.
                by_code: dict[str, list[dict]] = {}
                for r in line_rows:
                    code = str(r.get("SeriesCode") or "")
                    by_code.setdefault(code, []).append(r)
                code = max(by_code, key=lambda c: len(by_code[c])) if by_code else ""
                series_rows = by_code.get(code) or []
                if not series_rows:
                    continue
                payload["components"][label] = _series_payload(
                    label, code or f"T20600_L{line}", series_rows, months_back
                )
                if payload["components"][label]["latest_date"]:
                    latest_date_global = max(
                        latest_date_global,
                        payload["components"][label]["latest_date"],
                    )
            if latest_date_global:
                payload["as_of"] = latest_date_global
            return render_small_result(
                payload,
                response_format,
                title="BEA personal income snapshot",
                what="personal income",
            )
        except Exception as exc:
            return wrap_error(exc)
