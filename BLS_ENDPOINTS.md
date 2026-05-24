# BLS MCP Server — Tool → Endpoint Map

Authoritative mapping of every tool in this server to its underlying BLS
data source. The BLS Public Data API has exactly one endpoint
(`/publicAPI/v{1,2}/timeseries/data/`); the difference between tools is
which body parameters they set and how the response is reshaped.

Global notes:
- v2 (POST) requires `BLS_API_KEY`; v1 (GET) is the fallback (25/day,
  10-year cap, no `catalog`/`calculations`/`annualaverage`/`aspects`).
- v2 caps: 500 queries/day, 50 series per request, 20-year span per
  request. The client chunks longer ranges automatically.
- Series IDs are alphanumeric (3–30 chars). Validation regex:
  `^[A-Z0-9]{3,30}$`. Series IDs are normalized to uppercase.

---

## 1. API surface

### `POST https://api.bls.gov/publicAPI/v2/timeseries/data/`

Request body (JSON):

| Field | Type | Description |
| --- | --- | --- |
| `seriesid` | `list[str]` | 1–50 BLS series IDs. |
| `registrationkey` | `str` | The `BLS_API_KEY`. |
| `startyear` | `str` (YYYY) | Earliest year to include. Optional. |
| `endyear` | `str` (YYYY) | Latest year to include. Optional. |
| `catalog` | `bool` | Include the series catalog block (title, units, area, item, …). |
| `calculations` | `bool` | Include net/percent change calculations for 1/3/6/12 periods. |
| `annualaverage` | `bool` | Include the M13 annual-average pseudo-period. |
| `aspects` | `bool` | Include per-observation aspect metadata (survey-specific). |

Response envelope:

```jsonc
{
  "status": "REQUEST_SUCCEEDED",
  "message": [],
  "Results": {
    "series": [
      {
        "seriesID": "CUUR0000SA0",
        "catalog": { /* present when catalog=true */ },
        "data": [
          {
            "year": "2024", "period": "M12", "periodName": "December",
            "value": "319.799",
            "footnotes": [{...}],
            "latest": "true",
            "aspects": [/* present when aspects=true */],
            "calculations": {
              "net_changes": {"1": "...", "3": "...", "6": "...", "12": "..."},
              "pct_changes": {"1": "...", "3": "...", "6": "...", "12": "..."}
            }
          }
        ]
      }
    ]
  }
}
```

Period codes are reshaped to ISO dates by `transform.period_to_iso_date`:
`M01..M12` → first of the month, `M13` → Dec 31, `Q01..Q04` → first of the
quarter, `S01/S02` → Jan 1 / Jul 1, `A01` → Jan 1.

---

## 2. Tool → API parameter map

### Primitives — `tools/series.py`

#### `bls_get_series`
- Sets: `seriesid`, `startyear?`, `endyear?`, `catalog`, `calculations`,
  `annualaverage`, `aspects`.
- Knobs: `calculation_periods` (post-fetch filter); `expose_metadata`
  (controls whether the metadata block is included in the rendered output).
- Output: list of `{series_id, title, units, seasonal_adjustment,
  metadata?, observations: [{date, year, period, period_name, value,
  footnotes, latest, aspects?, net_change_{1,3,6,12}m,
  pct_change_{1,3,6,12}m}]}`.

#### `bls_get_latest_observation`
- Single-series convenience wrapper. Fetches with `catalog=true` and
  `calculations=true` when a key is set; returns just the last observation.

#### `bls_get_latest_observations` (plural)
- Multi-series convenience. One v2 call, no year bounds. Returns a list of
  `{series_id, title, date, value, net_change_1m, pct_change_1m,
  pct_change_12m}`.

#### `bls_get_series_metadata`
- Sets: `seriesid=[id]`, `catalog=true`. Returns the catalog block only.
  Requires v2.

#### `bls_list_popular_series`
- No API call. Returns the curated `catalog.popular.POPULAR_SERIES` dict
  organized by category.

### Discovery (pure local — no API call) — `tools/discovery.py`

| Tool | Sources |
| --- | --- |
| `bls_search_series` | `POPULAR_SERIES` + `cpi_areas`, `cpi_items`, `ces_supersectors`, `laus_states`. |
| `bls_build_series_id` | `builders/{cpi,ces,laus}.py` validating against embedded code tables. |
| `bls_describe_series` | Local decoder via `classify_series_id`; optional `verify=True` adds a v2 catalog call. |
| `bls_list_areas` | `cpi_areas.CPI_AREAS`, `laus_areas.LAUS_STATES`. |
| `bls_list_items` | `cpi_items.CPI_ITEMS`, `ces_industries.CES_SUPERSECTORS` / `ces_datatypes.CES_DATATYPES`, `laus_measures.LAUS_MEASURES`. |

### Analytics — `tools/analytics.py`

All analytics tools call `series._fetch_all_series` and apply pure pandas
transforms.

| Tool | Math |
| --- | --- |
| `bls_compose_panel` | Long-form → wide-form pivot (`pivot_to_panel`). Writes CSV+Parquet via the shared dataset writer. |
| `bls_transform_series` | `yoy` (`pct_change(12)*100`), `mom`, `mom_annualized` (`((1+m)^12-1)*100`), `log_diff`, `index` (rebase to 100 at `base_period`). |
| `bls_deflate_series` | `real = nominal / (deflator / deflator_at_base)`. Returns nominal + real series and their 12-month YoY %. |

### Composites — `tools/composites.py`

Each composite makes **one** v2 POST and applies analytics in-process.

#### `bls_inflation_snapshot`
- Series IDs (SA default): `CUSR0000SA0`, `CUSR0000SA0L1E`, `CUSR0000SAF1`,
  `CUSR0000SA0E`, `CUSR0000SAH1`, `CUSR0000SASLE`.
- Output per component: `{name, series_id, latest_date, latest_value,
  yoy_pct, mom_annualized_pct, history}`.

#### `bls_labor_market_snapshot`
- Always: `LNS14000000` (U-3), `LNS13327709` (U-6), `LNS11300000` (LFPR),
  `LNS12300000` (emp-pop), `CES0000000001` (payrolls), `CES0500000003`
  (AHE), `CES0500000002` (AWH).
- With `include_jolts=True`: `JTS000000000000000JOR` (openings rate),
  `JTS000000000000000QUR` (quits rate).
- Extra: `payrolls_3m_avg_change` — mean of the last three monthly level
  diffs in nonfarm payrolls.

#### `bls_real_wages`
- Defaults: nominal = `CES0500000003`, deflator = `CUSR0000SA0`.
- Returns `{wage_series_id, cpi_series_id, as_of, latest_real_yoy_pct,
  latest_nominal_yoy_pct, history: [{date, nominal_wage, cpi,
  real_wage_index, nominal_yoy_pct, real_yoy_pct}]}`. The
  `real_wage_index` starts at 100.0 at the earliest date in the lookback
  window.

---

## 3. Series ID encodings

### CPI: `CU/CW/SU + U/S + R + <area:4> + <item:variable>`
- Prefix:
  - `CU` = All Urban Consumers (CPI-U)
  - `CW` = Urban Wage Earners (CPI-W)
  - `SU` = Chained CPI-U (C-CPI-U)
- Seasonal: `U` = NSA, `S` = SA. Periodicity char: `R` (regular monthly).
- Examples:
  - `CUUR0000SA0` — CPI-U, NSA, US city average, All items
  - `CUSR0000SA0L1E` — CPI-U, SA, US city avg, Core (less food & energy)
  - `CUUR0400SA0` — CPI-U, NSA, West region, All items

### CES: `CES/CEU + supersector(2) + industry(6) + datatype(2)` (13 chars)
- Prefix `CES` is the SA-friendly path; `CEU` is the NSA full path.
- Seasonal flag is fused into the prefix (`CES` = SA, `CEU` = NSA) in our
  builder's output (the actual layout is `CE + S/U + ...`).
- Examples:
  - `CES0000000001` — SA, total nonfarm, all-industry, all employees
  - `CES0500000003` — SA, total private, AHE all employees
  - `CES3000000001` — SA, manufacturing, all-industry, all employees

### LAUS: `LA + S/U + <area:15> + <measure:2>` (20 chars)
- Seasonal: `S` = SA, `U` = NSA. State area code: `ST<FIPS>00000000000`.
- Measure: `03` = unemployment rate, `04` = unemployment level, `05` =
  employment level, `06` = labor force level.
- Example: `LASST480000000000003` — Texas SA unemployment rate.

### Other survey prefixes (decoded locally; builders are follow-ups)
- `LNS`/`LNU` — CPS (household survey). Used by U-1…U-6, LFPR, etc.
- `JTS`/`JTU` — JOLTS.
- `WPS`/`WPU`/`PCU`/`WDU` — PPI.
- `PRS`/`PRU` — Productivity & Costs.
- `CIS`/`CIU` — Employment Cost Index.
- `EIU` — Import/Export price indexes.

---

## 4. Catalog tables (embedded)

| File | Source | Notes |
| --- | --- | --- |
| `catalog/cpi_areas.py` | https://download.bls.gov/pub/time.series/cu/cu.area | Subset: US, regions, size classes, top metros. |
| `catalog/cpi_items.py` | https://download.bls.gov/pub/time.series/cu/cu.item | Subset: aggregates + most-requested detailed items. |
| `catalog/ces_industries.py` | https://download.bls.gov/pub/time.series/ce/ce.supersector | Supersector-level codes. |
| `catalog/ces_datatypes.py` | https://download.bls.gov/pub/time.series/ce/ce.datatype | All 11 standard data types. |
| `catalog/laus_areas.py` | https://download.bls.gov/pub/time.series/la/la.area | States only. County-level is voluminous. |
| `catalog/laus_measures.py` | https://download.bls.gov/pub/time.series/la/la.measure | All standard measures. |
| `catalog/popular.py` | Curated | ~60 widely-used series across all surveys. |

Tables are static and embedded at build time. To regenerate, write/run a
`scripts/refresh_bls_catalog.py` offline (not on the runtime path).

---

## 5. Rate limits and chunking

| Bound | v1 | v2 |
| --- | --- | --- |
| Daily queries | 25 | 500 |
| Series per request | 1 | 50 |
| Year span per request | 10 | 20 |
| Catalog / calculations / annual-average / aspects | n/a | yes |

`client.fetch` reuses `turningbull_mcp.http.backoff_seconds()` for 429/5xx
exponential backoff. `_fetch_all_series` chunks along both axes (50 IDs ×
20 years) and merges observations on `seriesID`.

---

## 6. Composite recipes (quick reference)

```
bls_inflation_snapshot()
  └─ POST /v2/timeseries/data/ with 6 CPI SA series
     └─ yoy(12), mom_annualized for each

bls_labor_market_snapshot(include_jolts=True)
  └─ POST /v2/timeseries/data/ with 7 CPS+CES series (+2 JOLTS)
     └─ 1m level diff, 1m %, 12m %, 3m avg payrolls change

bls_real_wages()
  └─ POST /v2/timeseries/data/ with [CES0500000003, CUSR0000SA0]
     └─ deflate(nominal=AHE, deflator=CPI), index → 100 at start, YoY
```
