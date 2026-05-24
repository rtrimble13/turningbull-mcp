# AG MCP Server — Tool → CLI-Subcommand Map

Authoritative mapping of every tool in this server to the underlying `ag`
CLI subcommand from the
[arima-garch](https://github.com/) project. Unlike the FMP/BLS/BEA
connectors, the AG connector does NOT talk to a remote HTTP API — it
shells out to a local C++ binary built from source.

Global notes:

- The CLI binary path is resolved from `$AG_BINARY_PATH` (preferred) or
  `shutil.which("ag")`. If neither resolves, every tool returns a clear
  "build the binary first" error.
- The connector reads/writes only inside `$AG_OUTPUT_DIR`
  (default `./ag_output`). Subdirectories are created on first use.
- Subprocess wall-clock timeout is `$AG_SUBPROCESS_TIMEOUT` seconds
  (default 600). On timeout the tool returns an `AGError` advising how
  to shrink the work (smaller grid, switch from `criterion=CV` to
  `criterion=BIC`, fewer paths, etc.).
- Every tool is annotated `readOnlyHint=True`, `destructiveHint=False`,
  `idempotentHint=True`, `openWorldHint=True`. Writes are scoped to
  `$AG_OUTPUT_DIR`, matching the FMP/BLS/BEA convention for summary-mode
  artifacts.
- The CLI's stdout is the analyst-readable report; every tool returns it
  verbatim under `raw_stdout` for transparency AND a flat `parsed` block
  with the structured fields (log-likelihood, AIC/BIC, ARIMA/GARCH
  params, Ljung-Box and Jarque-Bera p-values, persistence, the Student-t
  recommendation) so the LLM never has to scrape free text.

---

## 1. Output-directory layout

```
$AG_OUTPUT_DIR/
├── prices/      # raw price CSVs from FMP (one row per day)
├── series/      # raw series CSVs from BLS/BEA (date,value,…)
├── returns/     # derived log/simple returns CSVs (input to `ag fit`)
├── models/      # fitted model JSONs
├── forecasts/   # forecast CSVs from `ag forecast`
├── simulations/ # simulation CSVs from `ag simulate` / `ag sim`
└── diagnostics/ # diagnostics JSONs from `ag diagnostics`
```

Filenames are deterministic and human-readable, e.g.
`models/NVDA_arima101_garch11_gaussian_<hash>.json`,
`forecasts/NVDA_arima101_garch11_gaussian_<hash>_h22.csv`,
`returns/NVDA_log_returns.csv`. Re-running the same workflow overwrites
the same files (filename-based natural dedup).

---

## 2. Returns-preprocessing conventions

`ag fit -d <data.csv>` expects a stationary series. The connector owns
this conversion via `ag_prepare_returns` and the `ag_load_series` shortcut.

| `return_type` | Formula | When to use |
| --- | --- | --- |
| `log` (default for prices) | `r_t = ln(p_t / p_{t-1})` | Equities / ETFs / FX / crypto prices from FMP. Symmetric, additive across time, GARCH-standard. |
| `simple` | `r_t = (p_t - p_{t-1}) / p_{t-1}` | Discrete percent returns when log-additivity isn't useful. |
| `none` (default for macro) | pass-through | BLS YoY series, BEA growth rates, anything already in % change. |

**Annualization factor** is inferred from the median date spacing:

| Cadence | Factor |
| --- | --- |
| daily | 252 |
| weekly | 52 |
| monthly | 12 |
| quarterly | 4 |
| annual | 1 |

Override via the `annualization_factor` parameter on data-prep tools
when the auto-inference is wrong (e.g. a daily series with weekends
dropped that happens to look like a 5-day spacing).

---

## 3. Tool → CLI map

### Primitives (1:1 with subcommands)

| Tool | CLI subcommand | Notes |
| --- | --- | --- |
| `ag_fit` | `ag fit -d <data> --arima p,d,q --garch p,q -o <model.json> --innovation X [--t-df N]` | Writes one model JSON. Defaults to `gaussian`; parses Student-t recommendation from stdout. |
| `ag_select` | `ag select -d <data> -o <model.json> --max-p N --max-d N --max-q N --max-garch-p N --max-garch-q N --criterion BIC` | Defaults `max_p=max_q=2, max_d=1, max_garch_p=max_garch_q=1`. `criterion=CV` is slow. |
| `ag_forecast` | `ag forecast -m <model.json> --horizon N -o <forecast.csv>` | `annualize=True` reports annualized stdev in the summary; the CSV stays per-period. |
| `ag_simulate` | `ag simulate -m <model.json> --paths N --length N -o <sim.csv> --seed N [--stats]` | Default `mode="summary"` (CSV path + parsed stats). `mode="inline"` caps rows at 5000. |
| `ag_diagnostics` | `ag diagnostics -m <model.json> -d <data.csv> [-o <diag.json>]` | Parses Ljung-Box (raw + squared residuals) and Jarque-Bera p-values. |
| `ag_sim_from_spec` | `ag sim --arima p,d,q --garch p,q --length N -o <data.csv> --seed N --innovation X` | Synthesize a series from a bare spec; no model JSON required. |
| `ag_describe_model` | _(local read)_ | Read a saved model JSON; no subprocess. |
| `ag_list_models` | _(local read)_ | Scan `$AG_OUTPUT_DIR/models/`; no subprocess. |

### Data preparation

| Tool | What it does |
| --- | --- |
| `ag_prepare_returns` | Convert an existing prices CSV (e.g. one written by `fmp_get_historical_prices`) into a returns CSV under `$AG_OUTPUT_DIR/returns/`. |
| `ag_load_series` | Direct-from-source pull. `source="fmp_prices"` reuses `FMP_API_KEY` and calls FMP's `/stable/historical-price-eod/full`; `source="bls_series"` reuses `BLS_API_KEY` (v2) with v1 fallback; `source="bea_series"` reuses `BEA_API_KEY` (`extras` must include `dataset` + dataset-specific params per `BEA_ENDPOINTS.md`). |

### Composite analyst tools

| Tool | Pipeline | Key response fields |
| --- | --- | --- |
| `ag_volatility_snapshot` | FMP prices → log returns → `ag select` (BIC) → `ag diagnostics` → `ag forecast(22)`. | `model`, `diagnostics`, `model_adequate` (bool + reasons), `distribution_recommendation` (with exact rerun command), current conditional vol (per-period + annualized), forecast (h1/h5/h22 variance + annualized stdev), `artifacts` paths. |
| `ag_var_snapshot` | Same prep + `ag_select` → `ag_simulate(paths, horizon)` → empirical quantile of cumulative returns. Also computes parametric Gaussian VaR for comparison. | `empirical_var`, `empirical_es`, `parametric_var`, `fat_tail_uplift`, dollar-scaled versions, `warnings` (model-inadequacy, Student-t recommended but fit Gaussian, persistence near 1.0). |
| `ag_forecast_distribution` | Same prep + `ag_select` (or load a saved model JSON) → `ag_simulate(paths, horizon)` → quantiles at each step. | Quantile fan (`q05, q10, q25, q50, q75, q90, q95`) per horizon step; simulation CSV path. |
| `ag_compare_volatility` | Per symbol: same prep + `ag_fit(1,0,1)(1,1)` (or `ag_select` if `criterion ≠ "fixed"`). | Ranked table by GARCH persistence; per-row n_obs, annualized realized vol, annualized unconditional vol, distribution_used, student_t_recommended, input excess kurtosis, model_adequate. |
| `ag_macro_volatility_snapshot` | Same as `ag_volatility_snapshot` but source is BLS/BEA. Default `return_type="none"`. | Same shape; `macro_source` tag added. |
| `ag_stress_test` | Same prep + `ag_fit(1,0,1)(1,1)` under the chosen innovation (`gaussian`/`student_t_df5`/`student_t_df3`) → `ag_simulate(paths=5000, length=horizon)`. | Return distribution at horizon (`p01,p05,p10,p50,p90,p95,p99`), `prob_loss_gt_{5,10,20}pct`, worst/best terminal return. |

---

## 4. Diagnostic gating

Every composite that produces a forecast or VaR carries a top-level
`model_adequate: bool` plus `model_adequate_reasons: list[str]`. The
rules:

| Check | Threshold | Effect |
| --- | --- | --- |
| Ljung-Box on squared residuals (GARCH adequacy) | p > 0.05 | Required. If p ≤ 0.05 → `model_adequate=false`, residual ARCH remains. |
| GARCH persistence (α+β) | < 0.999 | Required. ≥ 0.999 → `model_adequate=false`, multi-step variance does not converge. |
| Optimizer convergence | True | Required. |
| Ljung-Box on raw residuals | p > 0.05 | Surfaced, not gating (ARIMA can sometimes leave mean-equation autocorrelation). |
| Jarque-Bera (residual normality) | p > 0.05 | Surfaced as `distribution_recommendation` rather than gating. |

When Student-t is recommended but the model was fit Gaussian, the
`distribution_recommendation` block includes the exact `ag_fit(...)`
call that would refit with the suggested degrees of freedom. The
connector does NOT auto-refit; that's the caller's decision.

---

## 5. Stdout parsing (what the connector pulls out of the CLI report)

`interpretation.parse_fit_stdout` extracts:

- Information criteria: `log_likelihood`, `aic`, `bic`, `aicc`.
- ARIMA params: `intercept`, `ar_coef`, `ma_coef`.
- GARCH params: `omega`, `alpha_coef`, `beta_coef`.
- Diagnostic p-values: `ljung_box_residuals_pvalue`,
  `ljung_box_squared_residuals_pvalue`, `jarque_bera_pvalue`.
- Convergence: `converged: bool`.
- Distribution: `distribution_used`, `student_t_recommended`,
  `student_t_df_suggested`.
- Derived: `garch_persistence`, `near_unit_root`, `mean_reverting`,
  `unconditional_variance`.

When a field can't be parsed the dict simply doesn't carry the key —
callers must use `.get(field)` and treat absence as "unknown" rather
than zero.

For model JSONs (schema documented in `arima-garch/docs/file_formats.md`),
the JSON is authoritative. `parse_model_json` flattens it into the same
shape as the stdout parse so callers see a single dict.

---

## 6. Out of scope

- **Python bindings to the C++ library.** Subprocess is simpler and
  keeps the build trivial.
- **`ag-viz` wrapping.** Claude renders its own charts off the CSVs.
- **Multivariate / DCC-GARCH.** The underlying library is univariate.
  Portfolio-level work requires user-supplied correlations or
  univariate aggregation.
- **Caching with TTLs.** Filename-based natural dedup is sufficient for
  v1.
- **Auto-refit on Student-t recommendation.** Surfaced, never executed.
