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

### Inspect with the MCP Inspector

```sh
npx @modelcontextprotocol/inspector uv run python -m fmp_mcp.server
# or:
npx @modelcontextprotocol/inspector uv run python -m bls_mcp.server
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
