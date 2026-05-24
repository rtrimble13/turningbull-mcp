# BEA MCP Server — Tool → Endpoint Map

Authoritative mapping of every tool in this server to the underlying BEA
Data API. The BEA API has exactly one endpoint
(`https://apps.bea.gov/api/data`); requests are dispatched by the
`method` and `DataSetName` query parameters.

Global notes:
- Every call requires `UserID` (the BEA term for the API key) —
  register a free 36-character key at
  <https://apps.bea.gov/API/signup/> and set `BEA_API_KEY` in `.env`.
  There is no anonymous fallback.
- Responses are JSON when `ResultFormat=JSON` (the only format the
  connector uses).
- BEA throttles at **100 requests / minute**, **100 MB / minute**, and
  **30 errors / minute**. On a 429 the response includes a
  `Retry-After` header; the client honors it via
  `BEAClient._sleep_for`.

---

## 1. API surface

### `GET https://apps.bea.gov/api/data`

Query parameters (always present):

| Parameter | Value |
| --- | --- |
| `UserID` | 36-character API key (from `$BEA_API_KEY`). |
| `method` | One of `GetDataSetList`, `GetParameterList`, `GetParameterValues`, `GetParameterValuesFiltered`, `GetData`. |
| `DataSetName` | Dataset name (omitted for `GetDataSetList`). |
| `ResultFormat` | `JSON`. |

Plus dataset/method-specific parameters merged on top.

Response envelope:

```jsonc
{
  "BEAAPI": {
    "Request": {
      "RequestParam": [{ "ParameterName": "...", "ParameterValue": "..." }]
    },
    "Results": {
      "Statistic": "Gross Domestic Product",
      "UTCProductionTime": "...",
      "Dimensions": [
        { "Name": "TableName", "DataType": "string", "IsValue": "0" },
        { "Name": "SeriesCode", "DataType": "string", "IsValue": "0" },
        // ...
      ],
      "Data": [
        {
          "TableName": "T10101",
          "SeriesCode": "A191RL",
          "LineNumber": "1",
          "LineDescription": "Gross domestic product",
          "TimePeriod": "2024Q3",
          "METRIC_NAME": "Percent Change From Preceding Period",
          "CL_UNIT": "Percent",
          "UNIT_MULT": "0",
          "DataValue": "2.8",
          "NoteRef": "T10101"
        }
        // ...
      ],
      "Notes": [{ "NoteRef": "T10101", "NoteText": "Real GDP..." }]
    }
  }
}
```

Errors come back two ways:

- **HTTP status** (`401` invalid UserID, `404` bad URL, `429` rate-limited,
  `5xx` server error) — handled by `errors.map_http_error`.
- **In-envelope** on HTTP 200 — `BEAAPI.Results.Error` (or
  `BEAAPI.Error`) with `APIErrorCode` + `APIErrorDescription`. Handled by
  `BEAClient._extract_results`.

TimePeriod parsing (`transform.time_period_to_iso`):

| Token | ISO date |
| --- | --- |
| `2024` | `2024-01-01` |
| `2024Q1` | `2024-01-01` |
| `2024Q3` | `2024-07-01` |
| `2024M07` | `2024-07-01` |

`DataValue` is a string and may contain commas, `(D)` (suppressed), or
`(NA)`. `transform._coerce_value` returns `None` for non-numeric values.

---

## 2. Tool → API parameter map

### Discovery — `tools/discovery.py`

| Tool | BEA method | Params set | Result shape |
| --- | --- | --- | --- |
| `bea_list_datasets` | `GetDataSetList` | none | `Results.Dataset[]` → `{DatasetName, DatasetDescription}` |
| `bea_list_parameters` | `GetParameterList` | `DataSetName` | `Results.Parameter[]` → `{ParameterName, ParameterDataType, ParameterDescription, ParameterIsRequiredFlag, ParameterDefaultValue, MultipleAcceptedFlag, AllValue}` |
| `bea_list_parameter_values` | `GetParameterValues` | `DataSetName`, `ParameterName` | `Results.ParamValue[]` — codes + descriptions for that parameter |
| `bea_list_parameter_values_filtered` | `GetParameterValuesFiltered` | `DataSetName`, `TargetParameter`, plus arbitrary filters via the `filters` dict | `Results.ParamValue[]` constrained by the filter parameters |
| `bea_search_tables` | _none — pure local_ | n/a | Ranked subset of `bea_mcp.catalog.POPULAR_TABLES` |

### Generic — `tools/generic.py`

| Tool | BEA method | Params set | Result shape |
| --- | --- | --- | --- |
| `bea_get_data` | `GetData` | `DataSetName` + arbitrary user-supplied params dict | Flattened `Results.Data[]` rows (each gets ISO `date` and numeric `value`) |

### Per-dataset typed tools

Each calls `method=GetData` with `DataSetName` set to the dataset
indicated by the tool name. The dataset's accepted parameters are exposed
as typed function arguments.

#### `tools/national.py`

| Tool | Dataset | Required params | Optional params |
| --- | --- | --- | --- |
| `bea_get_nipa` | `NIPA` | `TableName`, `Frequency` | `Year` (default `LAST10`), `ShowMillions` |
| `bea_get_ni_underlying_detail` | `NIUnderlyingDetail` | `TableName`, `Frequency` | `Year` |
| `bea_get_fixed_assets` | `FixedAssets` | `TableName` | `Year` (default `ALL`) |

#### `tools/regional.py`

| Tool | Dataset | Required params |
| --- | --- | --- |
| `bea_get_regional` | `Regional` | `TableName`, `LineCode`, `GeoFips`, `Year` |

`GeoFips` accepts 5-digit FIPS codes (`06000` for California, `01001` for
Autauga County, AL), comma-separated lists, or one of the tokens
`STATE`, `COUNTY`, `MSA`, `MIC`, `CSA`, `PORT`, `DIV`, `NSA`.

#### `tools/industry.py`

| Tool | Dataset | Required params |
| --- | --- | --- |
| `bea_get_gdp_by_industry` | `GDPbyIndustry` | `TableID` (int), `Frequency`, `Industry`, `Year` |
| `bea_get_underlying_gdp_by_industry` | `UnderlyingGDPbyIndustry` | `TableID`, `Frequency`, `Industry`, `Year` |
| `bea_get_input_output` | `InputOutput` | `TableID`, `Year` |

#### `tools/international.py`

| Tool | Dataset | Required params |
| --- | --- | --- |
| `bea_get_ita` | `ITA` | `Indicator`, `AreaOrCountry`, `Frequency`, `Year` |
| `bea_get_iip` | `IIP` | `TypeOfInvestment`, `Component`, `Frequency`, `Year` |
| `bea_get_intl_serv_trade` | `IntlServTrade` | `TypeOfService`, `TradeDirection`, `Affiliation`, `AreaOrCountry`, `Year` |
| `bea_get_intl_serv_sta` | `IntlServSTA` | `Channel`, `Destination`, `Industry`, `AreaOrCountry`, `Year` |
| `bea_get_mne` | `MNE` | `DirectionOfInvestment`, `OwnershipLevel`, `Classification`, `SeriesID`, `Country`, `Industry`, `State`, `NonbankAffiliatesOnly`, `Year` |

### Composites — `tools/composites.py`

Each composite makes 1-3 `GetData` calls and assembles a structured
dashboard. All transforms (period parsing, YoY) happen in-process.

| Tool | Calls | Output |
| --- | --- | --- |
| `bea_gdp_snapshot` | NIPA T10101 (Q) + NIPA T10102 (Q) | Real GDP % change + contributions from PCE / Investment / Net X / Government, with history. |
| `bea_trade_balance_snapshot` | ITA (5 indicators in one call) + IIP (best-effort) | Current account, goods, services, secondary income; IIP change in position when available. |
| `bea_regional_snapshot` | Regional SAGDP9N, LineCode=1 | Real GDP by state — latest level, prior-year level, YoY % growth, ranked. |
| `bea_personal_income_snapshot` | NIPA T20600 (M) | Personal income, DPI, outlays, savings rate, each with history and YoY. |

---

## 3. Popular table cheat-sheet

The embedded `bea_mcp.catalog.POPULAR_TABLES` map covers the most-asked
tables across datasets. `bea_search_tables` ranks them by query
relevance. Highlights:

| Dataset | Table | Description |
| --- | --- | --- |
| NIPA | `T10101` | % Change From Preceding Period in Real GDP |
| NIPA | `T10102` | Contributions to % Change in Real GDP |
| NIPA | `T10105` | GDP (current $) |
| NIPA | `T10106` | Real GDP (chained $) |
| NIPA | `T11400` | Corporate Profits by Industry |
| NIPA | `T20100` | Personal Income and Its Disposition |
| NIPA | `T20600` | Personal Income, Monthly |
| NIPA | `T20305` | PCE by Major Type of Product |
| NIPA | `T20804` | PCE Price Indexes (PCE inflation) |
| Regional | `SAGDP1` | State GDP summary |
| Regional | `SAGDP9N` | Real GDP by state |
| Regional | `CAINC1` | Personal income summary by county/state |
| Regional | `CAINC4` | Personal income & employment by component |
| Regional | `SAEMP25N` | Full + part-time employment by state |
| GDPbyIndustry | `1` | Value Added by Industry |
| GDPbyIndustry | `5` | Value Added as % of GDP |
| GDPbyIndustry | `15` | Gross Output by Industry |
| FixedAssets | `FAAt101` | Net stock of fixed assets, current cost |
| ITA | `BalCurrAcct` | Balance on current account |
| ITA | `BalGds` / `BalServ` / `BalGdsServ` | Trade balances |
| IIP | `IIPNetPos` | Net international investment position |

For anything outside this list, use:

```text
bea_list_parameter_values(dataset="NIPA", parameter="TableName")
```

---

## 4. Rate limits and retry behavior

| Bound | Limit |
| --- | --- |
| Requests per minute | 100 |
| Data volume per minute | 100 MB |
| Errors per minute | 30 |
| HTTP 429 retry header | `Retry-After` (seconds) |

`BEAClient._get` reuses `turningbull_mcp.http.backoff_seconds()` for
generic exponential backoff and additionally honors `Retry-After` on
429s (`BEAClient._sleep_for` returns
`max(Retry-After, backoff_seconds(attempt))`).

---

## 5. Composite recipes (quick reference)

```
bea_gdp_snapshot()
  └─ GET /api/data?method=GetData&DataSetName=NIPA&TableName=T10101&Frequency=Q
  └─ GET /api/data?method=GetData&DataSetName=NIPA&TableName=T10102&Frequency=Q
     └─ headline + contributions, YoY history

bea_trade_balance_snapshot()
  └─ GET ITA Indicator=BalCurrAcct,BalGds,BalServ,BalGdsServ,BalSecondaryInc
  └─ GET IIP TypeOfInvestment=FinAssetsExclFinDeriv (best-effort)
     └─ trade balance components + IIP change

bea_regional_snapshot(geo_fips="STATE")
  └─ GET Regional TableName=SAGDP9N&LineCode=1&GeoFips=STATE
     └─ rank states by YoY real-GDP growth

bea_personal_income_snapshot()
  └─ GET NIPA T20600 (monthly)
     └─ income / DPI / outlays / savings rate dashboard
```
