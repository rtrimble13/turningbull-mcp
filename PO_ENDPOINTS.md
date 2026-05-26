# po_mcp endpoint catalogue

Maps each MCP tool exposed by `po_mcp` to the underlying `po` CLI
subcommand or `portopt` Python function. 27 tools total: 9 CLI
primitives, 6 closed-form portfolio constructions (portopt-only), 5
data / utility tools, and 7 analyst composites.

All tools are read-only. The CLI tools shell out to `$PO_BINARY_PATH`;
the portopt-supplement tools lazy-import `portopt` from `PYTHONPATH`.

## Data input convention

Every CLI tool accepts either:

- `data`: an inline assets-payload dict `{assets: [{ticker, ...}],
  covariance: [[...]], market_weights?, benchmark_weights?,
  risk_free_rate?}` (validated against `AssetDataInline`); materialized
  to `$PO_OUTPUT_DIR/tmp/data_<sha1>.json` before `po` is invoked.
  Identical payloads dedup to the same file.
- `data_path`: an absolute path to an existing JSON / CSV file on disk.

Exactly one of the two must be supplied. With `returns_mode=True`, the
input is interpreted as a periodic-returns CSV and `po` estimates μ / Σ
via the chosen shrinkage estimator.

## Output directory layout

```
$PO_OUTPUT_DIR/
├── data/        assets.json datasets written by po_estimate_covariance / composites
├── params/      MVO + BL params files (content-hashed)
├── results/     single-portfolio result JSONs
├── frontiers/   efficient-frontier CSVs
├── reports/     Jupyter HTML + notebook from po_report
├── backtests/   walk-forward equity curves, trades, summaries
└── tmp/         content-hashed JSON materialized from inline `data` payloads
```

## CLI primitives — `tools/primitives.py`

| Tool | `po` subcommand | Notes |
| --- | --- | --- |
| `po_mvo` | `po mvo -d ... [-p ...] -o ... -f json` | Single mean-variance optimal portfolio. Surfaces `total_capital`, `risk_aversion`, `risk_free_rate`, `turnover_penalty`, `budget`, `shrinkage`, `shrinkage_delta`, `periods_per_year`, `returns_mode`. |
| `po_frontier` | `po frontier ... -f csv` | Efficient frontier (forces CSV output). |
| `po_min_variance` | `po min-variance ...` | Global minimum-variance portfolio. |
| `po_max_sharpe` | `po max-sharpe ...` | Tangency portfolio. |
| `po_target_volatility` | `po target-vol --target X ...` | Fixed-volatility portfolio (annualized). |
| `po_target_return` | `po target-return --target X ...` | Fixed-return portfolio (annualized). |
| `po_black_litterman` | `po bl -d ... -p ... [...--show-model]` | BL single optimal; requires `params.views`. |
| `po_bl_frontier` | `po bl-frontier ... -f csv` | BL efficient frontier. |
| `po_report` | `po report -d ... -o <dir> -m mvo\|bl\|both` | Jupyter HTML + executed notebook. |

## Portopt-supplement portfolios — `tools/portfolios.py`

All require `portopt` to be importable.

| Tool | `portopt` function | Output |
| --- | --- | --- |
| `po_equal_risk_contribution` | `portopt.portfolios.equal_risk_contribution` | Risk-parity weights + per-asset risk contributions. |
| `po_hierarchical_risk_parity` | `portopt.portfolios.hierarchical_risk_parity` | HRP weights. |
| `po_inverse_variance` | `portopt.portfolios.inverse_variance` | `w ∝ 1/σ²`. |
| `po_inverse_volatility` | `portopt.portfolios.inverse_volatility` | `w ∝ 1/σ`. |
| `po_equal_weight` | (pure-Python, no portopt) | `1/N` weights. |
| `po_max_diversification` | `portopt.portfolios.maximum_diversification` | Maximizes `(w·σ) / σ_port`. |

Every output dict includes `weights`, `metrics` (vol, diversification
ratio, effective N, max position, gross exposure), and `risk_contributions`.

## Data / utility tools — `tools/data.py`

| Tool | Calls | Output |
| --- | --- | --- |
| `po_estimate_covariance` | `portopt.estimation.from_returns` | Writes assets.json to `$PO_OUTPUT_DIR/data/`; returns the path. |
| `po_summarize_portfolio` | `portopt.analytics.*` + pure helpers | Expected return, Sharpe, diversification ratio, effective N, active share, tracking error, beta, risk contributions. |
| `po_validate_data` | pure-local (NumPy Cholesky check) | List of validation issues (empty = clean). |
| `po_list_results` | filesystem scan | Per-result summary (label, n_assets, top holdings, metrics, created_at). |
| `po_describe_result` | filesystem read | Full result JSON (weights + metrics + raw_json). |

## Analyst composites — `tools/composites.py`

| Tool | Composition |
| --- | --- |
| `po_construct_portfolio` | Estimate → optimize via chosen `method` (mvo, max_sharpe, min_variance, target_vol, target_return, risk_parity, hrp, equal_weight, inverse_variance, inverse_volatility, max_diversification) → summarize. One-shot "build me a portfolio from these returns". |
| `po_compare_methods` | Estimate once; run every requested method on the same Σ/μ; rank by Sharpe. Returns turnover-vs-equal-weight per method. |
| `po_efficient_frontier_with_targets` | Frontier + per-target `target-vol`/`target-return` portfolios. |
| `po_walk_forward_backtest` | `portopt.backtest.walk_forward` with rolling estimation + transaction-cost-aware rebalancing; returns equity curve + summary (CAGR, Sharpe, Sortino, max drawdown, tracking error, IR). |
| `po_risk_attribution` | `portopt.attribution.brinson_fachler` / `brinson_hood_beebower`. |
| `po_stress_test_portfolio` | Apply per-scenario shocks to (μ, Σ) → re-summarize; report worst-case row by Sharpe. |
| `po_black_litterman_views_workflow` | Build `BlackLittermanParams` from views → materialize → `po bl`. |
