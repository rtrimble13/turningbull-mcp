"""BLS series-discovery tools.

All tools in this module are pure local — no HTTP, no ``BLS_API_KEY``
required. They search and decode against the embedded code tables in
:mod:`bls_mcp.catalog`.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..builders import (
    build_ces_series_id,
    build_cpi_series_id,
    build_laus_series_id,
    decode_ces_series_id,
    decode_cpi_series_id,
    decode_laus_series_id,
)
from ..catalog import POPULAR_SERIES, Survey, classify_series_id
from ..catalog.ces_datatypes import CES_DATATYPES
from ..catalog.ces_industries import CES_INDUSTRIES, CES_SUPERSECTORS
from ..catalog.cpi_areas import CPI_AREAS
from ..catalog.cpi_items import CPI_ITEMS
from ..catalog.laus_areas import LAUS_STATES
from ..catalog.laus_measures import LAUS_MEASURES
from ..client import get_client
from ..models import ResponseFormat, SeriesID
from ..transform import reshape_series
from ._common import READ_ONLY, render_small_result, wrap_error


def _flatten_popular() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, entries in POPULAR_SERIES.items():
        for e in entries:
            rows.append({"category": category, **e})
    return rows


def _score(query: str, *fields: str) -> int:
    """Cheap substring scoring: count of query tokens that appear in any field."""
    q = query.lower().strip()
    if not q:
        return 0
    tokens = [t for t in q.split() if t]
    hay = " ".join(f or "" for f in fields).lower()
    score = sum(1 for t in tokens if t in hay)
    # Boost: full-query substring match.
    if q in hay:
        score += 2
    return score


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="bls_search_series",
        annotations=READ_ONLY,
        description=(
            "Search the embedded BLS catalog (popular series + CPI/CES/LAUS "
            "code tables) for series matching a query. Pure local search — "
            "no HTTP call, no BLS_API_KEY needed. Returns a ranked list of "
            "[{series_id, title, survey, ...}] plus matched-code suggestions "
            "(e.g. CPI areas, CES industries) when the query hits a code "
            "table."
        ),
    )
    async def bls_search_series(
        query: Annotated[
            str,
            Field(description="Free-text query, e.g. 'core CPI' or 'Texas unemployment'."),
        ],
        survey: Annotated[
            Survey | None,
            Field(default=None, description="Filter results to one survey."),
        ] = None,
        limit: Annotated[
            int,
            Field(default=25, ge=1, le=200, description="Max results to return."),
        ] = 25,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            q = query.strip()
            if not q:
                raise ValueError("query must not be empty")

            # Score every popular series entry.
            scored: list[tuple[int, dict[str, str]]] = []
            for entry in _flatten_popular():
                if survey is not None and entry.get("survey") != survey.value:
                    continue
                s = _score(q, entry.get("title", ""), entry.get("notes", ""),
                           entry.get("id", ""), entry.get("category", ""))
                if s > 0:
                    scored.append((s, entry))
            scored.sort(key=lambda x: -x[0])
            series_hits = [e for _, e in scored[:limit]]

            # Also match against code tables for richer suggestions.
            code_hits: dict[str, list[dict[str, str]]] = {}
            if survey is None or survey == Survey.CPI:
                cpi_areas = [
                    {"code": k, "name": v} for k, v in CPI_AREAS.items()
                    if _score(q, v, k) > 0
                ]
                cpi_items = [
                    {"code": k, "name": v} for k, v in CPI_ITEMS.items()
                    if _score(q, v, k) > 0
                ]
                if cpi_areas:
                    code_hits["cpi_areas"] = cpi_areas[:limit]
                if cpi_items:
                    code_hits["cpi_items"] = cpi_items[:limit]
            if survey is None or survey == Survey.CES:
                ces_super = [
                    {"code": k, "name": v} for k, v in CES_SUPERSECTORS.items()
                    if _score(q, v, k) > 0
                ]
                if ces_super:
                    code_hits["ces_supersectors"] = ces_super[:limit]
            if survey is None or survey == Survey.LAUS:
                laus_states = [
                    {"code": k, "name": v} for k, v in LAUS_STATES.items()
                    if _score(q, v, k) > 0
                ]
                if laus_states:
                    code_hits["laus_states"] = laus_states[:limit]

            payload: dict[str, Any] = {
                "query": q,
                "series": series_hits,
                "total_series_hits": len(scored),
            }
            if code_hits:
                payload["code_hits"] = code_hits

            return render_small_result(
                payload,
                response_format,
                title=f"BLS search: {q}",
                what=q,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_build_series_id",
        annotations=READ_ONLY,
        description=(
            "Construct a valid BLS series ID for CPI, CES, or LAUS from "
            "human-readable inputs. Pure local — validates against the "
            "embedded code tables and returns a structured error with "
            "suggestions on a bad code. Currently supports CPI (area + "
            "item), CES (supersector + industry + datatype), and LAUS "
            "(state FIPS or area_code + measure)."
        ),
    )
    async def bls_build_series_id(
        survey: Annotated[
            Survey,
            Field(description="Which survey to build for: CPI, CES, or LAUS."),
        ],
        # CPI
        cpi_area_code: Annotated[
            str | None,
            Field(default=None, description="CPI area code (e.g. '0000' for US city avg)."),
        ] = None,
        cpi_item_code: Annotated[
            str | None,
            Field(default=None, description="CPI item code (e.g. 'SA0', 'SA0L1E')."),
        ] = None,
        cpi_seasonal: Annotated[
            str,
            Field(default="NSA", description="'NSA' or 'SA'."),
        ] = "NSA",
        cpi_consumer_group: Annotated[
            str,
            Field(default="U", description="'U' (All Urban Consumers) or 'W' (Wage Earners)."),
        ] = "U",
        # CES
        ces_supersector: Annotated[
            str | None,
            Field(default=None, description="CES supersector (e.g. '00' total nonfarm)."),
        ] = None,
        ces_industry: Annotated[
            str,
            Field(default="00000000", description="CES industry (6 or 8 chars)."),
        ] = "00000000",
        ces_datatype: Annotated[
            str | None,
            Field(default=None, description="CES datatype (e.g. '01' all-employees, '03' AHE)."),
        ] = None,
        ces_seasonal: Annotated[
            str,
            Field(default="SA", description="'SA' or 'NSA'."),
        ] = "SA",
        # LAUS
        laus_state_fips: Annotated[
            str | None,
            Field(default=None, description="2-digit state FIPS (e.g. '48' for Texas)."),
        ] = None,
        laus_area_code: Annotated[
            str | None,
            Field(default=None, description="Full 15-char LAUS area code (alternative to state_fips)."),
        ] = None,
        laus_measure: Annotated[
            str | None,
            Field(default=None, description="LAUS measure (e.g. '03' unemp rate)."),
        ] = None,
        laus_seasonal: Annotated[
            str,
            Field(default="SA", description="'SA' or 'NSA'."),
        ] = "SA",
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if survey == Survey.CPI:
                if cpi_area_code is None or cpi_item_code is None:
                    raise ValueError("CPI requires cpi_area_code and cpi_item_code.")
                result = build_cpi_series_id(
                    area_code=cpi_area_code,
                    item_code=cpi_item_code,
                    seasonal=cpi_seasonal,  # type: ignore[arg-type]
                    consumer_group=cpi_consumer_group,  # type: ignore[arg-type]
                )
            elif survey == Survey.CES:
                if ces_supersector is None or ces_datatype is None:
                    raise ValueError("CES requires ces_supersector and ces_datatype.")
                result = build_ces_series_id(
                    supersector=ces_supersector,
                    industry=ces_industry,
                    datatype=ces_datatype,
                    seasonal=ces_seasonal,  # type: ignore[arg-type]
                )
            elif survey == Survey.LAUS:
                if laus_measure is None:
                    raise ValueError("LAUS requires laus_measure.")
                if laus_state_fips is None and laus_area_code is None:
                    raise ValueError("LAUS requires laus_state_fips or laus_area_code.")
                result = build_laus_series_id(
                    state_fips=laus_state_fips,
                    area_code=laus_area_code,
                    measure=laus_measure,
                    seasonal=laus_seasonal,  # type: ignore[arg-type]
                )
            else:
                raise ValueError(
                    f"builder not yet implemented for survey={survey.value!r}. "
                    "Supported: CPI, CES, LAUS."
                )
            return render_small_result(
                result,
                response_format,
                title=f"Built {survey.value} series ID",
                what=str(result.get("series_id", "")),
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_describe_series",
        annotations=READ_ONLY,
        description=(
            "Decode a BLS series ID into its components (survey, seasonal "
            "flag, area/item/industry, measure) using local code tables. "
            "Free, fast, no API call. Set verify=True to also fetch the "
            "official catalog from the BLS v2 endpoint (requires "
            "BLS_API_KEY)."
        ),
    )
    async def bls_describe_series(
        series_id: Annotated[
            SeriesID,
            Field(description="A BLS series ID, e.g. CUUR0000SA0."),
        ],
        verify: Annotated[
            bool,
            Field(
                description=(
                    "If true, also fetch the official catalog metadata via "
                    "the BLS v2 endpoint."
                )
            ),
        ] = False,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            survey = classify_series_id(series_id)
            decoded: dict[str, Any]
            if survey == Survey.CPI:
                decoded = decode_cpi_series_id(series_id)
            elif survey == Survey.CES:
                decoded = decode_ces_series_id(series_id)
            elif survey == Survey.LAUS:
                decoded = decode_laus_series_id(series_id)
            else:
                decoded = {
                    "decoded": False,
                    "series_id": series_id,
                    "survey": survey.value,
                    "reason": (
                        f"survey {survey.value!r} has no local decoder yet; "
                        "use verify=True to fetch the official catalog."
                    ),
                }

            if verify:
                client = get_client()
                if not client.using_v2:
                    decoded["verify_error"] = (
                        "verify=True requires BLS_API_KEY (v2 catalog endpoint)."
                    )
                else:
                    raw = await client.fetch([series_id], catalog=True)
                    if raw:
                        shaped = reshape_series(raw[0])
                        decoded["official_catalog"] = {
                            "title": shaped.get("title"),
                            "units": shaped.get("units"),
                            "seasonal_adjustment": shaped.get("seasonal_adjustment"),
                            "metadata": shaped.get("metadata"),
                        }
            return render_small_result(
                decoded,
                response_format,
                title=f"Describe: {series_id}",
                what=series_id,
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_list_areas",
        annotations=READ_ONLY,
        description=(
            "List embedded area / state codes for a survey. Returns "
            "[{code, name}] filtered by an optional query. Pure local."
        ),
    )
    async def bls_list_areas(
        survey: Annotated[
            Survey,
            Field(description="Which survey: CPI or LAUS."),
        ],
        query: Annotated[
            str | None,
            Field(default=None, description="Substring filter on the name."),
        ] = None,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if survey == Survey.CPI:
                table = CPI_AREAS
            elif survey == Survey.LAUS:
                table = LAUS_STATES
            else:
                raise ValueError(
                    f"no area table for survey={survey.value!r}. Supported: CPI, LAUS."
                )
            q = (query or "").strip().lower()
            rows = [
                {"code": code, "name": name}
                for code, name in table.items()
                if not q or q in name.lower() or q in code.lower()
            ]
            return render_small_result(
                rows,
                response_format,
                title=f"{survey.value} areas ({len(rows)})",
                what=f"{survey.value} areas",
            )
        except Exception as exc:
            return wrap_error(exc)

    @mcp.tool(
        name="bls_list_items",
        annotations=READ_ONLY,
        description=(
            "List embedded item / data-type / measure codes for a survey. "
            "Returns [{code, name}] filtered by an optional query. Pure local. "
            "Supported: CPI (items), CES (supersectors / datatypes), LAUS (measures)."
        ),
    )
    async def bls_list_items(
        survey: Annotated[
            Survey,
            Field(description="Which survey: CPI, CES, or LAUS."),
        ],
        kind: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "For CES, choose 'supersectors' (default) or 'datatypes'. "
                    "Ignored for CPI and LAUS."
                ),
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(default=None, description="Substring filter on the name."),
        ] = None,
        response_format: Annotated[
            ResponseFormat,
            Field(description="markdown (default) or json."),
        ] = ResponseFormat.markdown,
    ) -> str:
        try:
            if survey == Survey.CPI:
                table = CPI_ITEMS
            elif survey == Survey.CES:
                table = CES_DATATYPES if (kind or "supersectors") == "datatypes" else CES_SUPERSECTORS
            elif survey == Survey.LAUS:
                table = LAUS_MEASURES
            else:
                raise ValueError(
                    f"no item table for survey={survey.value!r}. Supported: CPI, CES, LAUS."
                )
            q = (query or "").strip().lower()
            rows = [
                {"code": code, "name": name}
                for code, name in table.items()
                if not q or q in name.lower() or q in code.lower()
            ]
            return render_small_result(
                rows,
                response_format,
                title=f"{survey.value} items ({len(rows)})",
                what=f"{survey.value} items",
            )
        except Exception as exc:
            return wrap_error(exc)
