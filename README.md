# turningbull-mcp

A monorepo of MCP (Model Context Protocol) connectors that share a common
toolkit (HTTP retry, dataset output, response formatting, config loading).
Each connector is its own Python package under `src/` with its own
`server.py` entry point and console script.

## Connectors

| Connector | Package | Console script | Description |
| --- | --- | --- | --- |
| FMP | [`fmp_mcp`](src/fmp_mcp/) | `fmp-mcp` | [Financial Modeling Prep](https://site.financialmodelingprep.com/) stable API — prices, news, financials, screener, macro, indexes (27 tools). Endpoint catalogue in [`ENDPOINTS.md`](ENDPOINTS.md). |
| BLS | [`bls_mcp`](src/bls_mcp/) | `bls-mcp` | US [Bureau of Labor Statistics Public Data API v2](https://www.bls.gov/developers/) — CPI, unemployment, payrolls, PPI, productivity (4 tools). Works without a key via the v1 fallback. |

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
│   │   ├── client.py           # v1/v2 routing
│   │   ├── transform.py        # BLS period -> ISO date, value coercion
│   │   ├── models.py           # SeriesID, POPULAR_SERIES catalog
│   │   ├── errors.py
│   │   ├── output.py
│   │   ├── formatting.py
│   │   └── tools/series.py     # 4 tools (get_series, latest, popular, metadata)
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

## BLS-specific usage examples (in Claude)

The BLS connector wraps the [BLS Public Data API v2](https://www.bls.gov/developers/)
so you can pull headline economic time series — CPI, unemployment, payrolls,
PPI, productivity. A free v2 key (recommended) is available at
<https://data.bls.gov/registrationEngine/>; without one the server falls
back to v1 (25 queries/day, 10-year cap, no calculations/catalog) and logs
a warning at startup.

- **Latest reading**: "What's the latest CPI reading?"
  → `bls_get_latest_observation(series_id=CUUR0000SA0)`.
- **Compare series**: "Compare U-3 and U-6 unemployment since 2020."
  → `bls_get_series(series_ids=["LNS14000000","LNS13327709"],
  start_year=2020, include_calculations=true)`.
- **Single recent value**: "What was nonfarm payroll growth last month?"
  → `bls_get_latest_observation(series_id=CES0000000001)` and read the
  `pct_change_12m` field (or call `bls_get_series` with
  `include_calculations=true` for the 1-month change).
- **Discover series IDs**: "What BLS series should I use for core CPI?"
  → `bls_list_popular_series()` — a curated catalog grouped by Prices,
  Labor, Productivity.
