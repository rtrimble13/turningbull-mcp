# ag_mcp

ARIMA-GARCH MCP connector for the `turningbull-mcp` monorepo. Wraps the
[`arima-garch`](https://github.com/) C++ engine via its `ag` CLI as a
quant-developer toolkit: fit, select, forecast, simulate, and diagnose
univariate ARIMA-GARCH models. Designed to compose with the FMP / BLS /
BEA connectors so a single Claude turn can go from "symbol or series
ID" to "fitted model + diagnostics + forecast + VaR".

The endpoint catalogue (tool → CLI-subcommand map, output-directory
layout, returns-preprocessing conventions, diagnostic-gating rules) is
in [`AG_ENDPOINTS.md`](../../AG_ENDPOINTS.md).

## Prerequisite: build the `ag` binary

This connector does NOT ship the C++ engine — it shells out to it. Build
it first from the `arima-garch` repository (see that project's README
for build flags and OS-specific instructions). After a successful build
the binary is typically at:

```
<arima-garch>/build/ninja-release/src/ag
```

## Install

`ag_mcp` is built alongside the other connectors in this repo:

```sh
uv sync
```

No extra dependencies — `ag_mcp` shells out to the binary via
`asyncio.create_subprocess_exec` and otherwise uses the shared
`turningbull_mcp.*` toolkit plus pandas.

## Configure

Add to your repo-root `.env` (see `.env.example` for the full list):

```ini
# Required: absolute path to the compiled `ag` binary.
AG_BINARY_PATH=/full/path/to/arima-garch/build/ninja-release/src/ag

# Optional: directory for all persisted artifacts.
# Defaults to ./ag_output. Subdirectories (prices/, series/, returns/,
# models/, forecasts/, simulations/, diagnostics/) are created on first
# use.
AG_OUTPUT_DIR=./ag_output

# Optional: max wall-clock seconds per subprocess call.
AG_SUBPROCESS_TIMEOUT=600
```

`ag_load_series` and the composite tools also reuse the sibling
connectors' env vars (`FMP_API_KEY`, `BLS_API_KEY`, `BEA_API_KEY`) so a
single tool call can pull data + fit + forecast in one go.

## Run

Register with Claude Code:

```sh
claude mcp add ag -- uv run python -m ag_mcp.server
```

Or inspect with the MCP Inspector:

```sh
npx @modelcontextprotocol/inspector uv run python -m ag_mcp.server
```

## Smoke tests

```sh
AG_BINARY_PATH=/path/to/ag PYTHONPATH=src pytest tests/test_ag_smoke.py -q
```

The tests skip themselves if `AG_BINARY_PATH` is unset or the binary
doesn't exist, so a no-secret CI run stays green.

## What's in here

| File | Role |
| --- | --- |
| `server.py` | FastMCP instance + lifespan; resolves the `ag` binary and installs the runner singleton. |
| `runner.py` | `AGRunner` — async subprocess wrapper. One method per subcommand; each returns a small dataclass with raw stdout/stderr, the argv list, and a structured parse. Timeout/error mapping centralized here. |
| `interpretation.py` | Regex-based parsing of the CLI's stdout report (log-likelihood, AIC/BIC, ARIMA/GARCH params, Ljung-Box and Jarque-Bera p-values, Student-t recommendation) + flattening of the model JSON file. Derived fields (persistence = α+β, near-unit-root flag, unconditional variance) live here. |
| `preprocessing.py` | Returns conversion: prices → log/simple returns, BLS/BEA series → pass-through; cadence detection and annualization-factor lookup; sample stats. |
| `output.py` | `$AG_OUTPUT_DIR` resolution and per-subdirectory accessors. |
| `models.py` | Pydantic types (`ArimaOrder`, `GarchOrder`, `DataPath`, `ModelPath`, `Label`, `ReturnType`, `Frequency`, `InnovationDist`, `SelectionCriterion`). |
| `errors.py` | `AGError(ConnectorError)` + return-code mapping. |
| `registry.py` | Local read of `$AG_OUTPUT_DIR/models/*.json` — supports `ag_list_models` and `ag_describe_model`. |
| `tools/primitives.py` | 1:1 wrappers around each `ag` subcommand (8 tools). |
| `tools/data.py` | `ag_prepare_returns` + `ag_load_series` (FMP/BLS/BEA dispatch). |
| `tools/composites.py` | Analyst workflows: `ag_volatility_snapshot`, `ag_var_snapshot`, `ag_forecast_distribution`, `ag_compare_volatility`, `ag_macro_volatility_snapshot`, `ag_stress_test`. |

## Design notes

- **No pybind11.** The engine is invoked via subprocess. This keeps the
  Python build simple and lets the C++ engine evolve independently.
- **Single shared env.** Reuses the repo-wide `.env`; `ag_load_series`
  reuses the sibling connectors' API keys so the user doesn't have to
  spin up FMP/BLS/BEA servers separately when all they need is the data.
- **Diagnostic gating is first-class.** Every composite that produces a
  forecast or VaR has top-level `model_adequate: bool` and
  `model_adequate_reasons: list[str]`. The Ljung-Box squared-residuals
  p-value (the GARCH-adequacy gate) is never buried in free text.
- **Distribution recommendation, not auto-refit.** When the CLI flags
  Student-t as a better fit, the connector surfaces a structured
  `distribution_recommendation` block with the exact `ag_fit(...)`
  call that would refit. The caller decides.
- **Filename-based dedup.** Re-running the same workflow overwrites the
  same artifacts. No cache layer, no TTL, no metadata DB.
