# po_mcp

Portfolio-optimization MCP connector for the `turningbull-mcp` monorepo.
Wraps the [`po`](https://github.com/rtrimble13/po) C++ engine via its `po`
CLI for the 8 native optimization workflows (MVO, frontier, Black-
Litterman, BL frontier, min-variance, max-Sharpe, target-vol, target-
return, plus a Jupyter HTML report) and supplements them with a thin
lazy-loaded binding to the `portopt` Python library for HRP, ERC (risk
parity), inverse-var/vol, equal-weight, max-diversification, walk-
forward backtesting, Brinson attribution, and arbitrary-weights
portfolio summarization.

The endpoint catalogue (tool → CLI subcommand / `portopt` function map,
output-directory layout, data-input semantics) is in
[`PO_ENDPOINTS.md`](../../PO_ENDPOINTS.md).

## Prerequisite: build the `po` binary

This connector does NOT ship the C++ engine — it shells out to it. Build
it first from the `po` repository (see that project's README for build
flags and OS-specific instructions):

```sh
git clone https://github.com/rtrimble13/po
cd po
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

After a successful build the binary is at `<repo>/build/cli/po` and the
`portopt` Python extension (used by HRP / ERC / backtest / attribution /
summary tools) is under `<repo>/build/python/`.

The CLI tools work without `portopt`; the portopt-supplement tools error
with an actionable message if it isn't importable.

## Install

`po_mcp` is built alongside the other connectors in this repo:

```sh
uv sync
```

No new top-level dependency. Pandas / NumPy ship with the project for
the shared output layer; `portopt` is loaded lazily from `PYTHONPATH`
the first time a supplement tool is called.

## Configure

Add to your repo-root `.env` (see `.env.example` for the full list):

```ini
# Required: absolute path to the compiled `po` binary.
PO_BINARY_PATH=/full/path/to/po/build/cli/po

# Optional: directory for all persisted artifacts.
# Defaults to ./po_output. Subdirectories (data/, params/, results/,
# frontiers/, reports/, backtests/, tmp/) are created on first use.
PO_OUTPUT_DIR=./po_output

# Optional: max wall-clock seconds per subprocess call.
PO_SUBPROCESS_TIMEOUT=600
```

To enable the portopt-supplement tools, extend `PYTHONPATH` to include
the built extension when launching the server:

```sh
PYTHONPATH=/full/path/to/po/build/python:$PYTHONPATH \
  uv run python -m po_mcp.server
```

## Run

Register with Claude Code:

```sh
claude mcp add po -- uv run python -m po_mcp.server
```

To pass the binary path on registration, append
`-e PO_BINARY_PATH=/full/path/to/po`.

Or inspect with the MCP Inspector:

```sh
npx @modelcontextprotocol/inspector uv run python -m po_mcp.server
```

## Smoke tests

```sh
PO_BINARY_PATH=/path/to/po PYTHONPATH=src pytest tests/test_po_smoke.py -q
```

The tests skip themselves if `PO_BINARY_PATH` is unset or the binary
doesn't exist, so a no-secret CI run stays green. portopt-dependent
tests use `pytest.importorskip("portopt")` so a CLI-only install also
stays green.

## What's in here

| File | Role |
| --- | --- |
| `server.py` | FastMCP instance + lifespan; resolves the `po` binary and installs the runner singleton. |
| `runner.py` | `PORunner` — async subprocess wrapper. One method per `po` subcommand; each returns a small dataclass with raw stdout/stderr, the argv list, parsed weights/metrics/diagnostics, and the artifact path. Timeout / error mapping centralized here. |
| `pyengine.py` | Lazy wrapper around `portopt` for HRP, ERC, inverse-var/vol, equal-weight, max-diversification, walk-forward backtest, Brinson attribution, arbitrary-weights summary, and estimation-from-returns. `import portopt` deferred to first call so CLI-only installs still load. |
| `interpretation.py` | Parse the JSON / CSV artifacts `po` writes into flat weights/metrics/diagnostics blocks. Tolerates minor shape variation across `po` versions. |
| `models.py` | Pydantic types: `AssetDataInline` / `DataPathInput` / `DataInput` discriminated union, `OptimizationParams`, `BlackLittermanParams`, `View`, `GroupCap`, `Shrinkage`, `ConstructionMethod`, `AttributionMode`. Plus `materialize_data` / `materialize_params` helpers that content-address payloads into `$PO_OUTPUT_DIR/{tmp,params}/`. |
| `output.py` | `$PO_OUTPUT_DIR` resolution and per-subdirectory accessors. |
| `errors.py` | `POError(ConnectorError)` + return-code mapping + portopt-import error message. |
| `registry.py` | Local read of `$PO_OUTPUT_DIR/results/*.json` — supports `po_list_results` / `po_describe_result`. |
| `tools/primitives.py` | 9 tools — 1:1 wrappers around each `po` CLI subcommand. |
| `tools/portfolios.py` | 6 portopt-only closed-form constructions. |
| `tools/data.py` | 5 data / utility tools (estimate, summarize, validate, list, describe). |
| `tools/composites.py` | 7 analyst workflows (construct, compare, frontier+targets, walk-forward backtest, Brinson attribution, stress test, BL views workflow). |

## Design notes

- **CLI primary + Python supplement.** The `po` CLI is the source of
  truth for the 8 native optimization subcommands. The `portopt` Python
  module covers features the CLI doesn't expose (HRP, ERC, walk-forward,
  attribution). The two backends are isolated — a CLI-only install
  still loads the server cleanly; supplement tools error with an
  actionable message if `portopt` isn't importable.
- **Inline data or file path.** Every CLI tool accepts either an inline
  `data` JSON payload or a `data_path` to an existing file. Inline
  payloads are written to `$PO_OUTPUT_DIR/tmp/data_<sha1>.json` once
  per unique payload — identical inputs across calls dedup; mutations
  produce a new file. This keeps reruns deterministic and makes every
  artifact inspectable on disk.
- **Single shared env.** Reuses the repo-wide `.env`. No API keys
  required.
- **Deterministic filenames.** Every artifact under `$PO_OUTPUT_DIR/`
  is named either from a caller-supplied `label` or a content hash of
  the inputs, so re-running the same workflow overwrites the same file.
  No cache layer, no TTL, no metadata DB.
- **Read-only by default.** Every tool is annotated `READ_ONLY` (no
  destructive hint). The connector only writes artifacts under
  `$PO_OUTPUT_DIR/`.
- **stdio only.** Logs to stderr; stdout is reserved for MCP JSON-RPC.
