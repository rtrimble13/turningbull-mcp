# turningbull-mcp

A monorepo of MCP (Model Context Protocol) connectors that share a common
toolkit (HTTP retry, dataset output, response formatting, config loading).
Each connector is its own Python package under `src/` with its own
`server.py` entry point and console script.

## Connectors

| Connector | Package | Console script | Description |
| --- | --- | --- | --- |
| FMP | [`fmp_mcp`](src/fmp_mcp/) | `fmp-mcp` | [Financial Modeling Prep](https://site.financialmodelingprep.com/) stable API — prices, technical indicators, news, financials, valuation (DCF + Piotroski/Altman), analyst estimates, earnings transcripts, calendars, ownership (insider + 13F), SEC filings, ETFs, multi-asset, composite snapshots (97 tools). Endpoint catalogue in [`FMP_ENDPOINTS.md`](FMP_ENDPOINTS.md). |
| BLS | [`bls_mcp`](src/bls_mcp/) | `bls-mcp` | US [Bureau of Labor Statistics Public Data API v2](https://www.bls.gov/developers/) — CPI, unemployment, payrolls, PPI, productivity, JOLTS, ECI (16 tools spanning fetch, discovery, analytics, and composite snapshots). Endpoint catalogue in [`BLS_ENDPOINTS.md`](BLS_ENDPOINTS.md). Works without a key via the v1 fallback (discovery tools work key-less). |
| BEA | [`bea_mcp`](src/bea_mcp/) | `bea-mcp` | US [Bureau of Economic Analysis API](https://apps.bea.gov/API/bea_web_service_api_user_guide.htm) — national accounts (GDP, personal income, PCE, corporate profits), regional accounts (state/county GDP and income), GDP by industry, input-output tables, fixed assets, and international accounts (ITA, IIP, services, MNE). 22 tools spanning meta-discovery (four BEA meta methods + local table search), generic GetData, typed per-dataset wrappers for all 12 data datasets, and composite snapshots (GDP, trade balance, regional, personal income). Endpoint catalogue in [`BEA_ENDPOINTS.md`](BEA_ENDPOINTS.md). Requires a free 36-char [UserID](https://apps.bea.gov/API/signup/). |
| AG  | [`ag_mcp`](src/ag_mcp/) | `ag-mcp` | ARIMA-GARCH model fitting, selection, forecasting, simulation, and diagnostics on top of the `arima-garch` C++ engine (shelled out via the `ag` CLI). 16 tools: 8 primitives (1:1 CLI wrappers + describe/list helpers), 2 data-prep tools (returns conversion + direct FMP/BLS/BEA load), and 6 analyst composites (volatility snapshot, VaR snapshot, forecast distribution, volatility comparison, macro volatility snapshot, stress test). Designed to compose with FMP/BLS/BEA: a single Claude turn can go from "symbol or series ID" to "fitted model + diagnostics + forecast + VaR" with no manual file shuffling. Endpoint catalogue in [`AG_ENDPOINTS.md`](AG_ENDPOINTS.md). Requires building the C++ engine — see [arima-garch/README.md](https://github.com/) for the prerequisite. |
| PO  | [`po_mcp`](src/po_mcp/) | `po-mcp` | Portfolio construction and risk analysis on top of the [`po`](https://github.com/rtrimble13/po) C++ engine (CLI for the 8 native subcommands) plus a lazy-loaded `portopt` Python supplement (HRP, ERC/risk parity, walk-forward backtest, Brinson attribution, portfolio summary). 27 tools: 9 CLI primitives (mvo, frontier, bl, bl-frontier, min-variance, max-sharpe, target-vol, target-return, report), 6 closed-form constructions (ERC, HRP, inverse-var/vol, equal-weight, max-diversification), 5 data/utility tools (estimate-from-returns, summarize-portfolio, validate-data, list/describe-results), and 7 CFA composites (construct-portfolio, compare-methods, frontier-with-targets, walk-forward backtest, Brinson attribution, stress-test, BL views workflow). Both inline JSON and on-disk data inputs are supported; inline payloads are content-addressed under `$PO_OUTPUT_DIR/tmp/`. Endpoint catalogue in [`PO_ENDPOINTS.md`](PO_ENDPOINTS.md). Requires building the C++ engine — see [po/README.md](https://github.com/rtrimble13/po) for the prerequisite. |
| FRED | [`fred_mcp`](src/fred_mcp/) | `fred-mcp` | US [Federal Reserve (FRED) API](https://fred.stlouisfed.org/docs/api/fred/) — economic time series, categories, releases, sources, and tags. 35 tools covering the full core FRED API (Categories ×6, Releases ×9, Series ×10 incl. observations/search/vintages, Sources ×3, Tags ×3) plus the GeoFRED / FRED Maps regional-data API ×4 (shape files, series groups, series data, regional data). Endpoint catalogue in [`FRED_ENDPOINTS.md`](FRED_ENDPOINTS.md). Requires a free [`FRED_API_KEY`](https://fredaccount.stlouisfed.org/apikeys) — FRED rejects keyless requests, so the connector fails fast with a clear error when it is unset. |

To add a new connector, follow the recipe in [Adding a connector](#adding-a-connector).

## Requirements

- Python **3.11+**
- API keys for each connector you plan to run (e.g. `FMP_API_KEY`,
  optionally `BLS_API_KEY`)

## Install

### With `uv` (recommended)

```sh
uv sync
```

### With `pip` + venv

```sh
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e .
```

## Configure

A single repo-root `.env` is shared by every connector. Copy
[`.env.example`](.env.example) to `.env` and fill in the values for the
connectors you care about — each connector only reads its own namespaced
vars (e.g. `FMP_*`).

```ini
FMP_API_KEY=your_real_key_here
FMP_OUTPUT_DIR=./fmp_output     # optional
```

`.env` is loaded once at process start by the shared
`turningbull_mcp.config.load_env()` helper, so any connector launched from
this repo sees the same environment.

## Run a connector

### Register the FMP server with Claude Code

```sh
claude mcp add fmp -- uv run python -m fmp_mcp.server
```

Or, without uv:

```sh
claude mcp add fmp -- /full/path/to/.venv/Scripts/python -m fmp_mcp.server
```

### Register with Claude Desktop

Add to `claude_desktop_config.json` (Windows:
`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "fmp": {
      "command": "C:\\path\\to\\turningbull-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "fmp_mcp.server"],
      "env": {
        "FMP_API_KEY": "your_real_key_here",
        "FMP_OUTPUT_DIR": "C:\\path\\to\\turningbull-mcp\\fmp_output"
      }
    }
  }
}
```

Restart Claude Desktop after editing.

### Register the BLS server with Claude Code

```sh
claude mcp add bls -- uv run python -m bls_mcp.server
```

Or, without uv:

```sh
claude mcp add bls -- /full/path/to/.venv/Scripts/python -m bls_mcp.server
```

To pass the API key on registration, append `-e BLS_API_KEY=your_key`.

### Register BLS with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bls": {
      "command": "C:\\path\\to\\turningbull-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "bls_mcp.server"],
      "env": {
        "BLS_API_KEY": "your_real_key_here",
        "BLS_OUTPUT_DIR": "C:\\path\\to\\turningbull-mcp\\bls_output"
      }
    }
  }
}
```

`BLS_API_KEY` is optional — without it the server falls back to BLS v1
(25 queries/day, 10-year cap, no calculations/catalog). Register for a
free v2 key at <https://data.bls.gov/registrationEngine/>.

### Register the AG server with Claude Code

`ag_mcp` requires the compiled `ag` binary from the [arima-garch](https://github.com/)
project. Build it first (see that repo's README), then set
`AG_BINARY_PATH=/full/path/to/ag` in your `.env` (or place `ag` on
`PATH`). Once that's done:

```sh
claude mcp add ag -- uv run python -m ag_mcp.server
```

Or, without uv:

```sh
claude mcp add ag -- /full/path/to/.venv/Scripts/python -m ag_mcp.server
```

To pass the binary path on registration, append
`-e AG_BINARY_PATH=/full/path/to/ag`.

### Register AG with Claude Desktop

```json
{
  "mcpServers": {
    "ag": {
      "command": "C:\\path\\to\\turningbull-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ag_mcp.server"],
      "env": {
        "AG_BINARY_PATH": "C:\\path\\to\\arima-garch\\build\\ninja-release\\src\\ag.exe",
        "AG_OUTPUT_DIR": "C:\\path\\to\\turningbull-mcp\\ag_output"
      }
    }
  }
}
```

### Register the PO server with Claude Code

`po_mcp` requires the compiled `po` binary from the
[`po`](https://github.com/rtrimble13/po) portfolio-optimization project.
Build it first (see that repo's README), then set
`PO_BINARY_PATH=/full/path/to/po` in your `.env` (or place `po` on
`PATH`). Optionally extend `PYTHONPATH` to include the built `portopt`
Python extension so the HRP / ERC / walk-forward / attribution /
summary tools become available (CLI-only tools work without it). Once
that's done:

```sh
claude mcp add po -- uv run python -m po_mcp.server
```

To pass the binary path on registration, append
`-e PO_BINARY_PATH=/full/path/to/po`.

### Register PO with Claude Desktop

```json
{
  "mcpServers": {
    "po": {
      "command": "C:\\path\\to\\turningbull-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "po_mcp.server"],
      "env": {
        "PO_BINARY_PATH": "C:\\path\\to\\po\\build\\cli\\po.exe",
        "PO_OUTPUT_DIR": "C:\\path\\to\\turningbull-mcp\\po_output",
        "PYTHONPATH": "C:\\path\\to\\po\\build\\python"
      }
    }
  }
}
```

### Register the FRED server with Claude Code

`fred_mcp` wraps the St. Louis Fed [FRED API](https://fred.stlouisfed.org/docs/api/fred/).
A free API key is **required** — register at
<https://fredaccount.stlouisfed.org/apikeys> and set `FRED_API_KEY` in your
`.env` (FRED rejects keyless requests, so the tools fail fast with a clear
error when it is unset). Then:

```sh
claude mcp add fred -- uv run python -m fred_mcp.server
```

Or, without uv:

```sh
claude mcp add fred -- /full/path/to/.venv/Scripts/python -m fred_mcp.server
```

To pass the API key on registration, append `-e FRED_API_KEY=your_key`.

### Register FRED with Claude Desktop

```json
{
  "mcpServers": {
    "fred": {
      "command": "C:\\path\\to\\turningbull-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "fred_mcp.server"],
      "env": {
        "FRED_API_KEY": "your_real_key_here",
        "FRED_OUTPUT_DIR": "C:\\path\\to\\turningbull-mcp\\fred_output"
      }
    }
  }
}
```

### Inspect with the MCP Inspector

```sh
npx @modelcontextprotocol/inspector uv run python -m fmp_mcp.server
# or:
npx @modelcontextprotocol/inspector uv run python -m bls_mcp.server
# or:
npx @modelcontextprotocol/inspector uv run python -m ag_mcp.server
# or:
npx @modelcontextprotocol/inspector uv run python -m po_mcp.server
# or:
npx @modelcontextprotocol/inspector uv run python -m fred_mcp.server
```

## Test

Per-connector smoke tests live under `tests/`. Tests that hit a live API
skip themselves when their key is unset, so a no-secret CI run stays green.

```sh
PYTHONPATH=src pytest -q                  # all live-API tests skipped
FMP_API_KEY=... PYTHONPATH=src pytest -q  # full FMP smoke run
```

## Repo layout

```
turningbull-mcp/
├── ENDPOINTS.md                # FMP tool → endpoint map
├── README.md
├── pyproject.toml
├── .env.example                # shared env for every connector
├── src/
│   ├── turningbull_mcp/        # shared toolkit (no MCP server of its own)
│   │   ├── config.py           # one-shot .env loading, require_env()
│   │   ├── http.py             # httpx client factory + backoff helper
│   │   ├── output.py           # CSV/Parquet writer, inline_payload, output dir
│   │   ├── formatting.py       # markdown / json rendering
│   │   ├── models.py           # ResponseFormat, OutputMode, date validators
│   │   ├── tool_helpers.py     # READ_ONLY, chunk_date_range, render_*_result
│   │   ├── errors.py           # ConnectorError base, empty_result_message
│   │   └── logging.py          # stderr logger safe for MCP stdio
│   ├── bls_mcp/                # BLS connector (sibling package)
│   │   ├── server.py
│   │   ├── client.py           # v1/v2 routing (catalog/calculations/annualaverage/aspects)
│   │   ├── transform.py        # BLS period -> ISO date, value coercion, full calc grid
│   │   ├── models.py           # SeriesID, SeriesIDList, Survey enum
│   │   ├── errors.py
│   │   ├── output.py
│   │   ├── formatting.py
│   │   ├── catalog/            # Embedded BLS code tables (CPI/CES/LAUS/...)
│   │   ├── builders/           # CPI / CES / LAUS series-ID construction
│   │   └── tools/              # 16 tools across:
│   │       ├── series.py       #   fetch primitives
│   │       ├── discovery.py    #   search, build, describe (pure local)
│   │       ├── analytics.py    #   panel, transforms, deflate
│   │       └── composites.py   #   inflation / labor / real-wages snapshots
│   └── fmp_mcp/                # FMP connector (sibling package)
│       ├── server.py           # FastMCP instance + lifespan
│       ├── client.py           # FMPClient (composes shared http primitives)
│       ├── errors.py           # FMPError(ConnectorError), 401/403/… mapping
│       ├── models.py           # Symbol, SymbolList, Period, Interval, …
│       ├── output.py           # FMP_OUTPUT_DIR-flavored wrapper
│       ├── formatting.py       # back-compat re-export
│       └── tools/
│           ├── _common.py      # FMP-defaulted chunking + render_large_result
│           ├── prices.py
│           ├── news.py
│           ├── financials.py
│           ├── corporate.py
│           ├── classification.py
│           ├── indexes.py
│           ├── macro.py
│           └── screener.py
└── tests/
    └── test_smoke.py           # FMP live-API smoke tests
```

## Adding a connector

1. Create a sibling package `src/<name>_mcp/` mirroring `src/fmp_mcp/`:
   - `server.py` — FastMCP instance, lifespan, tool-module registration
   - `client.py` — API client; compose `turningbull_mcp.http.make_async_client`
     and `backoff_seconds`
   - `errors.py` — `class <Name>Error(ConnectorError)` + status-code mapper
   - `models.py` — domain-specific Pydantic types; re-export the generics
     you need from `turningbull_mcp.models`
   - `output.py` — thin wrapper that calls
     `turningbull_mcp.output.resolve_output_dir("<NAME>_OUTPUT_DIR", "./<name>_output")`
   - `tools/_common.py` — wrap `render_large_result` to inject your output
     dir; re-export `READ_ONLY`, `wrap_error`, etc. from
     `turningbull_mcp.tool_helpers`
   - `tools/*.py` — one module per topic, each exposing `register(mcp)`
2. Add a console script in `pyproject.toml`:
   ```toml
   [project.scripts]
   <name>-mcp = "<name>_mcp.server:main"
   ```
   and the package to the wheel build:
   ```toml
   [tool.hatch.build.targets.wheel]
   packages = ["src/turningbull_mcp", "src/fmp_mcp", "src/<name>_mcp"]
   ```
3. Add the connector's namespaced vars to [`.env.example`](.env.example).
4. Register the new server with Claude Code: `claude mcp add <name> -- uv run python -m <name>_mcp.server`.

## Design notes

- **Shared toolkit, isolated connectors.** Every connector composes the
  shared primitives but owns its own client, error mapping, and tool
  modules. Cross-connector coupling stays in `turningbull_mcp/`.
- **Single .env, namespaced vars.** One repo-root `.env` keeps shared keys
  (e.g. a future shared cache dir) in one place; connector-specific keys
  use a namespace prefix so they can't collide.
- **Read-only by default.** FMP tools are annotated `readOnlyHint=True`,
  `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=True`.
- **No cache.** Every call hits the upstream API live. The HTTP client
  retries 429/5xx with exponential backoff + jitter.
- **Large datasets.** Tools that can return many rows accept a `mode`
  parameter: `summary` (writes CSV+Parquet to the connector's output dir
  and returns a digest) or `inline` (returns rows, capped at 5000).
- **stdio only.** Each server logs to stderr; stdout is reserved for the
  MCP JSON-RPC stream.

## FMP-specific usage examples (in Claude)

- **Price history**: "Pull AAPL daily prices from 2015 through today."
  → `fmp_get_historical_prices(symbol=AAPL, from_date=2015-01-01, mode=summary)`
  writes a CSV+Parquet to `FMP_OUTPUT_DIR` and returns a digest.

- **Intraday**: "Get me 5-minute bars for ^GSPC for last week."
  → `fmp_get_intraday_prices(symbol=^GSPC, interval=5min, from_date=…)`.

- **News**: "What's the latest news on NVDA and AMD?"
  → `fmp_get_stock_news(symbols=NVDA,AMD)`.

- **Fundamentals**: "Show me Apple's last 10 annual income statements."
  → `fmp_get_income_statement(symbol=AAPL, period=annual, limit=10)`.

- **Screening**: "US Technology stocks over $1B market cap, beta < 1.2."
  → `fmp_screen_stocks(sector=Technology, country=US,
  market_cap_more_than=1_000_000_000, beta_lower_than=1.2)`.

- **Macro**: "Compare 10y treasury yield to CPI YoY for 2020–2024."
  → `fmp_get_treasury_rates(from_date=…, to_date=…)` plus
  `fmp_get_economic_indicator(name=CPI, from_date=…, to_date=…)`.

- **Technical indicators**: "Daily RSI(14) and 50/200-day SMAs for NVDA YTD."
  → `fmp_get_technical_indicator(symbol=NVDA, indicator=rsi,
  period_length=14, interval=1day, from_date=2026-01-01)` (and
  again with `indicator=sma`, `period_length=50` / `200`).

- **Earnings prep**: "Get me everything I need to write a preview for
  Apple's next earnings."
  → `fmp_earnings_prep(symbol=AAPL)` — next earnings date, last 4
  surprises, transcript dates, forward analyst estimates, and the
  current grade consensus, all in one call.

- **Valuation**: "Is Microsoft overvalued by DCF? Compare to peers."
  → `fmp_valuation_snapshot(symbol=MSFT)` — DCF + key metrics +
  price target consensus + peers + Piotroski/Altman scores +
  letter rating.

- **Earnings transcript**: "Pull the full transcript of NVDA's Q4 2025 call."
  → `fmp_get_earnings_transcript(symbol=NVDA, year=2025, quarter=4,
  mode=summary)` — writes the transcript text to `$FMP_OUTPUT_DIR`.

- **Insider trades**: "Has anyone at TSLA bought stock in the last
  90 days?"
  → `fmp_get_insider_trades(symbol=TSLA, transaction_type=P-Purchase)`.

- **13F holdings**: "What did Berkshire Hathaway own at end of Q4?"
  → `fmp_search_institution(name="Berkshire")` to get the CIK, then
  `fmp_get_form_13f(cik=…, year=2025, quarter=4, mode=summary)`.

- **Dividends & splits**: "Build a 20-year total-return series for KO."
  → `fmp_get_historical_prices(symbol=KO, from_date=2005-01-01,
  mode=summary)` + `fmp_get_dividend_history(symbol=KO, limit=200)`.

- **ETF flow analysis**: "What ETFs hold NVDA and how heavily?"
  → `fmp_get_etf_holders(symbol=NVDA)`. Reverse: "What's inside SPY?"
  → `fmp_get_etf_holdings(symbol=SPY, mode=summary)`.

- **SEC filings**: "Show me every 8-K NVDA filed in 2025."
  → `fmp_list_sec_filings(symbol=NVDA, form_type=8-K,
  from_date=2025-01-01)`.

- **Calendars**: "Which companies report earnings next week?"
  → `fmp_get_earnings_calendar(from_date=…, to_date=…)`.

- **Company one-pager**: "Give me the basics on PLTR."
  → `fmp_company_snapshot(symbol=PLTR)` — profile, quote, key metrics,
  analyst target, latest 3 headlines.

## BLS-specific usage examples (in Claude)

The BLS connector wraps the [BLS Public Data API v2](https://www.bls.gov/developers/)
across 16 tools spanning four areas: **fetch primitives**, **discovery**
(catalog + ID construction), **analytics** (panel, transforms,
deflation), and **composite dashboards**. A free v2 key (recommended) is
available at <https://data.bls.gov/registrationEngine/>; without one the
server falls back to v1 (25 queries/day, 10-year cap, no
calculations/catalog/aspects). **Discovery tools work without a key.**
See [`BLS_ENDPOINTS.md`](BLS_ENDPOINTS.md) for the full tool-to-API map
and series-ID encodings.

### Fetch primitives

- **Latest reading**: "What's the latest CPI reading?"
  → `bls_get_latest_observation(series_id=CUUR0000SA0)`.
- **Latest readings for many series in one call**:
  → `bls_get_latest_observations(series_ids="CUUR0000SA0,LNS14000000,CES0000000001")`.
- **Compare series with full calculations grid (1m/3m/6m/12m)**:
  → `bls_get_series(series_ids=["LNS14000000","LNS13327709"],
  start_year=2020, include_calculations=true,
  include_catalog=true, include_aspects=true)`.
- **Restrict calculations to a single period**:
  → `bls_get_series(..., include_calculations=true,
  calculation_periods=[12])`.

### Discovery (pure local — no API key needed)

- **Search the catalog**: "What series should I use for shelter inflation?"
  → `bls_search_series(query="shelter")`.
- **Build a series ID from human inputs**: "I want SA core CPI."
  → `bls_build_series_id(survey="CPI", cpi_area_code="0000",
  cpi_item_code="SA0L1E", cpi_seasonal="SA")` → `CUSR0000SA0L1E`.
- **Decode a series ID you already have**:
  → `bls_describe_series(series_id="LASST480000000000003")` → "LAUS, SA,
  Texas, Unemployment rate".
- **Browse area / item / measure codes**:
  → `bls_list_areas(survey="LAUS", query="texas")`,
  `bls_list_items(survey="CPI", query="rent")`.

### Analytics

- **Panel-data export for regression**: "Pull CPI, U-3, and payrolls
  monthly since 2010 as one aligned dataset."
  → `bls_compose_panel(series_ids=["CUUR0000SA0","LNS14000000","CES0000000001"],
  start_year=2010, mode=summary)` → writes CSV+Parquet to
  `$BLS_OUTPUT_DIR`.
- **Apply an econometric transform**: "Show CPI as YoY % change."
  → `bls_transform_series(series_id="CUUR0000SA0", transform="yoy",
  start_year=2000)`.
- **Real wages**: "Deflate AHE by CPI."
  → `bls_deflate_series(nominal_series_id="CES0500000003",
  deflator_series_id="CUSR0000SA0", start_year=2010)`.

### Composite dashboards

- **Inflation snapshot**: "Give me the latest inflation picture."
  → `bls_inflation_snapshot(months_back=12)` — headline, core, food,
  energy, shelter, services-less-energy with latest YoY and MoM
  annualized.
- **Labor market snapshot**: "How tight is the labor market?"
  → `bls_labor_market_snapshot(months_back=12, include_jolts=true)` —
  U-3, U-6, LFPR, employment-population ratio, payrolls, AHE, AWH,
  openings + quits rates, and the 3-month average payrolls change.
- **Real wage growth**: "Are wages outpacing inflation?"
  → `bls_real_wages(months_back=24)` — nominal AHE, CPI, real wage
  index rebased to 100, nominal & real YoY.

## BEA-specific usage examples (in Claude)

The BEA connector wraps the [BEA Data API](https://apps.bea.gov/API/bea_web_service_api_user_guide.htm)
across 22 tools spanning four areas: **discovery** (the four BEA meta
methods plus a local table search), **generic fetch** (a single
`bea_get_data` escape hatch), **typed per-dataset wrappers** (one per
dataset for NIPA, NIUnderlyingDetail, FixedAssets, Regional,
GDPbyIndustry, UnderlyingGDPbyIndustry, InputOutput, ITA, IIP,
IntlServTrade, IntlServSTA, MNE), and **composite dashboards** (GDP,
trade balance, regional, personal income). A free 36-character UserID is
required — register at <https://apps.bea.gov/API/signup/>. See
[`BEA_ENDPOINTS.md`](BEA_ENDPOINTS.md) for the full tool-to-API map.

### Discovery

- **What datasets does BEA expose?** → `bea_list_datasets()`.
- **What parameters does the Regional dataset take?**
  → `bea_list_parameters(dataset="Regional")`.
- **What TableNames exist in NIPA?**
  → `bea_list_parameter_values(dataset="NIPA", parameter="TableName")`.
- **What LineCodes are valid for Regional CAINC4?**
  → `bea_list_parameter_values_filtered(dataset="Regional",
  target_parameter="LineCode", filters={"TableName": "CAINC4"})`.
- **Pick a popular table quickly**:
  → `bea_search_tables(query="real GDP")` (pure local, no API call).

### National accounts

- **Headline GDP, quarterly**:
  → `bea_get_nipa(table_name="T10101", frequency="Q", year="LAST10")`.
- **Personal income detail, monthly**:
  → `bea_get_nipa(table_name="T20600", frequency="M", year="LAST5")`.
- **Corporate profits by industry**:
  → `bea_get_nipa(table_name="T11400", frequency="Q", year="LAST10")`.
- **Underlying detail (deeper PCE breakdown)**:
  → `bea_get_ni_underlying_detail(table_name="U70405", frequency="A",
  year="LAST10")`.
- **Fixed assets net stock**:
  → `bea_get_fixed_assets(table_name="FAAt101", year="LAST10")`.

### Regional accounts

- **Personal income by state**:
  → `bea_get_regional(table_name="CAINC4", line_code=1,
  geo_fips="STATE", year="LAST5")`.
- **Real GDP for one state (California)**:
  → `bea_get_regional(table_name="SAGDP9N", line_code=1,
  geo_fips="06000", year="LAST10")`.
- **County-level personal income (large — use summary)**:
  → `bea_get_regional(table_name="CAINC1", line_code=1,
  geo_fips="COUNTY", year="2023", mode="summary")`.

### Industry & input-output

- **Value added by industry, latest**:
  → `bea_get_gdp_by_industry(table_id=1, frequency="A",
  industry="ALL", year="LAST5")`.
- **Industry share of GDP**:
  → `bea_get_gdp_by_industry(table_id=5, frequency="A",
  industry="ALL", year="LAST10")`.
- **Industry-by-commodity total requirements (I-O)**:
  → `bea_get_input_output(table_id=56, year="LAST5",
  mode="summary")`.

### International accounts

- **Current account balance vs. China**:
  → `bea_get_ita(indicator="BalCurrAcct", area_or_country="China",
  frequency="A", year="LAST10")`.
- **Net international investment position**:
  → `bea_get_iip(type_of_investment="IIPNetPos", component="Pos",
  frequency="Q", year="LAST10")`.
- **Services trade with the EU**:
  → `bea_get_intl_serv_trade(type_of_service="AllServiceTypes",
  trade_direction="Balance", area_or_country="EuropeanUnion",
  year="LAST5")`.
- **US MNEs abroad — sales by country**:
  → `bea_get_mne(direction_of_investment="outward", series_id="8",
  classification="Country", year="LAST5")`.

### Composite dashboards

- **GDP snapshot**: "What's the latest GDP print and what drove it?"
  → `bea_gdp_snapshot(quarters_back=8)` — headline real GDP growth +
  contributions from PCE / investment / net exports / government.
- **Trade balance snapshot**: "How big is the current-account deficit?"
  → `bea_trade_balance_snapshot(years_back=5)` — current account,
  goods, services, secondary income, plus IIP change in position.
- **Regional snapshot**: "Which states grew fastest?"
  → `bea_regional_snapshot(geo_fips="STATE", years_back=5)` — ranked
  real-GDP growth across all states.
- **Personal income snapshot**: "How are households doing?"
  → `bea_personal_income_snapshot(months_back=24)` — personal income,
  DPI, savings rate, outlays.

### Escape hatch (any dataset)

- **Anything not covered by a typed tool**:
  → `bea_get_data(dataset="NIPA", params={"TableName": "T20305",
  "Frequency": "Q", "Year": "LAST10"})`.

## AG-specific usage examples (in Claude)

The AG connector wraps the [arima-garch](https://github.com/) C++ engine
via its `ag` CLI. Build the binary first (see that repo's README) and
set `AG_BINARY_PATH` in your `.env`. All persisted artifacts (raw
prices, derived returns, fitted models, forecasts, simulations,
diagnostics) live under `$AG_OUTPUT_DIR` in a fixed substructure. See
[`AG_ENDPOINTS.md`](AG_ENDPOINTS.md) for the full tool→CLI-subcommand
map and returns-preprocessing conventions.

### One-shot analyst workflows

- **Fit a GARCH model to NVDA daily returns and tell me if it's
  well-specified**:
  → `ag_volatility_snapshot(symbol="NVDA")` — pulls 5y FMP prices,
  converts to log returns, runs `ag select` (BIC), runs `ag
  diagnostics`, and runs `ag forecast` for 22 trading days. Response
  includes `model_adequate: bool`, the Ljung-Box² p-value (the GARCH-
  adequacy gate), persistence (with near-unit-root flag), and a
  Student-t recommendation block if the residuals call for it.

- **10-day 95% VaR on a $1M SPY position**:
  → `ag_var_snapshot(symbol="SPY", horizon_days=10, confidence=0.95,
  portfolio_value=1_000_000)` — runs an empirical Monte Carlo VaR
  against the parametric Gaussian VaR and reports the fat-tail uplift.
  Warns if the model uses Gaussian innovations but Student-t was
  recommended (tail risk understated).

- **Compare volatility clustering across FAANG**:
  → `ag_compare_volatility(symbols=["META","AAPL","AMZN","NFLX","GOOG"])`
  — ranked table by GARCH persistence (highest = strongest volatility
  clustering), with annualized realized vol, annualized unconditional
  vol (when defined), and a Student-t recommendation flag per name.

- **How persistent is core CPI inflation?**:
  → `ag_macro_volatility_snapshot(series_id="CUSR0000SA0L1E",
  source="bls", return_type="log")` — pulls 20 years of BLS core CPI,
  takes log differences, fits ARIMA-GARCH, and reports persistence and
  unconditional inflation variance. Monthly cadence auto-sets the
  annualization factor to 12.

- **Stress-test SPY under heavy tails**:
  → `ag_stress_test(symbol="SPY", scenario="student_t_df3")` — large
  MC under Student-t(3) innovations. Run the three scenarios
  (`gaussian`, `student_t_df5`, `student_t_df3`) and compare the
  return-distribution p1/p5 to see how much your tail-risk number
  depends on the innovation-distribution assumption.

### Data preparation

- **Convert an existing FMP prices CSV to log returns**:
  → `ag_prepare_returns(prices_csv_path="/path/to/NVDA_daily.csv",
  symbol_or_label="NVDA", return_type="log",
  price_column="adjClose")`.

- **Direct-from-source pull (no FMP server registration needed)**:
  → `ag_load_series(source="fmp_prices", identifier="SPY",
  from_date="2010-01-01")` (reuses `FMP_API_KEY`).

- **BLS series → returns CSV**:
  → `ag_load_series(source="bls_series", identifier="CUSR0000SA0L1E",
  from_date="2005-01", return_type="log")` (level series → log
  differences). For YoY series, drop `return_type` to use the
  default `"none"`.

### Primitives (use when the composite tools aren't a fit)

- `ag_fit(data_path="...", arima=[1,0,1], garch=[1,1],
  innovation="student_t", t_df=5)`.
- `ag_select(data_path="...", max_p=2, max_q=2, criterion="BIC")`.
- `ag_forecast(model_path="...", horizon=22, annualize=true)`.
- `ag_simulate(model_path="...", paths=2000, length=22, seed=42)`.
- `ag_diagnostics(model_path="...", data_path="...")`.
- `ag_describe_model(model_path="...")` — pure local file read.
- `ag_list_models()` — scan `$AG_OUTPUT_DIR/models/`.
- `ag_sim_from_spec(arima=[1,0,1], garch=[1,1], length=500)` — bare
  spec → synthetic series (useful for tests).

## PO-specific usage examples (in Claude)

The PO connector wraps the [`po`](https://github.com/rtrimble13/po)
portfolio-optimization C++ engine. Build the binary first and set
`PO_BINARY_PATH` in your `.env`. The 6 closed-form portfolios (HRP,
ERC, inverse-var/vol, equal-weight, max-diversification), the walk-
forward backtest, Brinson attribution, and the arbitrary-weights
summary tool additionally require the `portopt` Python extension on
`PYTHONPATH` (the CLI tools work without it). All artifacts —
materialized inline data, params files, optimization results, frontier
CSVs, Jupyter reports, walk-forward backtests — live under
`$PO_OUTPUT_DIR/`. See [`PO_ENDPOINTS.md`](PO_ENDPOINTS.md) for the
full tool → CLI subcommand / `portopt` function map.

### Mean-variance optimization (from inline data)

- **Build an MVO portfolio from a Σ + μ payload**:
  → `po_mvo(data={"assets": [{"ticker": "AAPL", "expected_return": 0.15},
  {"ticker": "MSFT", "expected_return": 0.12}, ...],
  "covariance": [[...], ...]}, risk_aversion=2.5)`. Returns weights,
  Sharpe, vol, diversification ratio; writes a result JSON under
  `$PO_OUTPUT_DIR/results/`.

### Mean-variance with constraints (sector caps + turnover penalty)

- **MVO with sector cap and turnover penalty**:
  → `po_mvo(data=..., params={"lower_bounds": 0.0, "upper_bounds": 0.4,
  "turnover_penalty": 0.01, "current_weights": {...},
  "groups": [{"description": "Tech ≤ 30%", "members": ["AAPL","MSFT","NVDA"],
  "upper": 0.30}]})`.

### Build a portfolio from a returns CSV (one-shot)

- **"Build me a max-Sharpe portfolio from these returns with Ledoit-Wolf
  shrinkage"**:
  → `po_construct_portfolio(returns_csv_path="/path/to/returns.csv",
  method="max_sharpe", shrinkage="ledoit-wolf", risk_free_rate=0.04)` —
  estimates μ, Σ → runs `po max-sharpe` → returns weights + metrics.

### Compare construction methods on the same returns set

- **"How does MVO compare to HRP and risk parity on this universe?"**:
  → `po_compare_methods(returns_csv_path="/path/to/returns.csv",
  methods=["mvo","max_sharpe","min_variance","risk_parity","hrp",
  "equal_weight","max_diversification"],
  shrinkage="ledoit-wolf")` — ranked by Sharpe, with per-method
  turnover-vs-equal-weight.

### Efficient frontier with highlighted target portfolios

- **"Build the frontier and pin the 10%, 15%, and 20% volatility
  portfolios"**:
  → `po_efficient_frontier_with_targets(data=...,
  target_vols=[0.10, 0.15, 0.20])` — returns the full frontier CSV +
  three `target-vol` portfolios with their weights.

### Black-Litterman with views

- **"Build a BL portfolio where I think AAPL outperforms MSFT by 3%
  with 70% confidence and Tech beats Energy by 5%"**:
  → `po_black_litterman_views_workflow(data=...,
  views=[{"pick_vector": {"AAPL": 1.0, "MSFT": -1.0},
  "expected_return": 0.03, "confidence": 0.70,
  "description": "AAPL > MSFT by 3%"}, {...}], tau=0.05,
  risk_aversion=2.5, confidence_mode="idzorek")`.

- **BL frontier with views**:
  → `po_bl_frontier(data=..., params={"tau": 0.05, "risk_aversion": 2.5,
  "confidence_mode": "idzorek", "views": [{...}]})`.

### Risk parity (equal risk contribution)

- **"Compute risk-parity weights for this covariance matrix"**:
  → `po_equal_risk_contribution(data={"assets":[...],
  "covariance":[[...]]})`. Returns weights, per-asset risk
  contributions, portfolio vol, diversification ratio, effective N.

### Hierarchical Risk Parity (HRP)

- **HRP weights** (robust on short / ill-conditioned samples):
  → `po_hierarchical_risk_parity(data=...)`.

### Walk-forward backtest with transaction costs

- **"Backtest a max-Sharpe strategy with monthly rebalancing and 5 bps
  transaction cost vs SPY"**:
  → `po_walk_forward_backtest(returns_csv_path="/path/to/returns.csv",
  strategy="max_sharpe", window=126, step=21,
  transaction_cost=0.0005, periods_per_year=252,
  shrinkage="ledoit-wolf",
  benchmark_returns_csv_path="/path/to/spy_returns.csv")` — returns
  equity curve, CAGR, Sharpe, Sortino, max drawdown, tracking error,
  information ratio.

### Brinson attribution

- **"Decompose active return between my portfolio and the benchmark by
  sector"**:
  → `po_risk_attribution(portfolio_group_weights={"Tech":0.45,
  "Energy":0.10, "Health":0.20, "Financials":0.25},
  benchmark_group_weights={...},
  portfolio_group_returns={...},
  benchmark_group_returns={...},
  mode="brinson_fachler")` — allocation + selection effects per
  sector and totals.

### Arbitrary-weights portfolio summary

- **"What's the Sharpe / vol / TE / beta of this candidate weights set?"**:
  → `po_summarize_portfolio(weights={"AAPL":0.4,"MSFT":0.4,"NVDA":0.2},
  data=..., benchmark_weights={...}, risk_free_rate=0.04)` — expected
  return, Sharpe, diversification ratio, effective N, active share,
  tracking error, beta, per-asset risk contributions.

### Stress test a portfolio

- **"What happens to my Sharpe if Tech drops 20% and volatility
  doubles?"**:
  → `po_stress_test_portfolio(weights={...}, data=...,
  shock_scenarios=[{"name": "tech-crash",
  "sector_shock": {"Tech": -0.20}, "covariance_multiplier": 2.0}])` —
  per-scenario metrics + worst-case row by Sharpe.

### Estimate Σ, μ from a returns CSV (chainable)

- **"Estimate covariance and write an assets.json I can reuse for
  multiple optimizations"**:
  → `po_estimate_covariance(returns_csv_path="/path/to/returns.csv",
  shrinkage="ledoit-wolf", periods_per_year=252)` — returns
  `data_path` pointing at the written assets.json that you can pass to
  any other PO tool via `data_path=...`.

### Validate inputs before paying for an optimization

- **"Check this Σ is PSD and the tickers line up before I run the
  optimizer"**:
  → `po_validate_data(data={"assets":[...], "covariance":[[...]]})`.

### Diagnostic Jupyter report

- **"Generate a full diagnostic HTML report for this portfolio"**:
  → `po_report(data=..., params=..., method="both")` — writes the
  HTML + executed notebook under `$PO_OUTPUT_DIR/reports/<label>/`.

### Browse / load past results

- `po_list_results()` — scan `$PO_OUTPUT_DIR/results/` and return a
  summary per persisted optimization.
- `po_describe_result(result_path="...")` — load one result JSON.

## FRED-specific usage examples (in Claude)

The FRED connector wraps the [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
across 35 tools spanning the full core API — **Categories**, **Releases**,
**Series**, **Sources**, **Tags** — plus the **GeoFRED / FRED Maps**
regional-data API. A free `FRED_API_KEY` is required (register at
<https://fredaccount.stlouisfed.org/apikeys>). Large list results
(observations, series searches, tag lists) accept a `mode` parameter:
`inline` (default) or `summary` (writes CSV+Parquet to `$FRED_OUTPUT_DIR`).
See [`FRED_ENDPOINTS.md`](FRED_ENDPOINTS.md) for the full tool→endpoint map.

### Series & observations

- **Pull a series' data**: "Get real GNP since 2000."
  → `fred_get_series_observations(series_id="GNPCA",
  observation_start="2000-01-01")`.
- **Transform on the fly**: "Show CPI as year-over-year percent change."
  → `fred_get_series_observations(series_id="CPIAUCSL", units="pc1")`.
- **Series metadata**: "What is series UNRATE?"
  → `fred_get_series(series_id="UNRATE")`.
- **Vintages / revisions**: "When was GDP revised?"
  → `fred_get_series_vintagedates(series_id="GDP")`.

### Discovery

- **Search**: "Find series about mortgage rates."
  → `fred_search_series(search_text="mortgage rate")`.
- **Browse categories**: "What's under the root category?"
  → `fred_get_category_children(category_id=0)`.
- **By tags**: "List series tagged monthly + nation."
  → `fred_get_tags_series(tag_names="monthly;nation")`.
- **Releases**: "What releases does FRED publish, and when?"
  → `fred_get_releases()` / `fred_get_releases_dates()`.
- **Sources**: "Who provides this data?"
  → `fred_get_sources()` and `fred_get_source_releases(source_id=1)`.

### GeoFRED (regional maps)

- **Series group metadata**: "Is per-capita personal income mappable?"
  → `fred_get_geofred_series_group(series_id="WIPCPI")`.
- **Regional data**: "Per-capita personal income by state for 2022."
  → `fred_get_geofred_regional_data(series_group="882",
  region_type="state", date="2022-01-01", season="NSA",
  units="Dollars")`.
- **Shape files**: "Get the state shape GeoJSON."
  → `fred_get_geofred_shapes(shape="state")`.
