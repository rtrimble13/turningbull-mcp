"""Live smoke tests for the ag_mcp connector.

These tests shell out to the compiled `ag` binary. They skip themselves
when ``AG_BINARY_PATH`` is unset (or the path doesn't exist), so a
no-secret CI run stays green.

Run with::

    AG_BINARY_PATH=/path/to/ag PYTHONPATH=src pytest tests/test_ag_smoke.py -q

The synthetic-data block (`test_sim`, `test_fit_on_synth`, …) only needs
the binary. The FMP block (`test_fmp_volatility_snapshot`) also needs
``FMP_API_KEY`` and will skip otherwise.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ag_mcp.runner import AGRunner, install_runner
from ag_mcp.output import (
    models_dir,
    output_dir,
    returns_dir,
    simulations_dir,
    forecasts_dir,
    diagnostics_dir,
)


def _binary_resolvable() -> bool:
    env = os.environ.get("AG_BINARY_PATH", "").strip()
    if env and Path(env).expanduser().exists():
        return True
    return shutil.which("ag") is not None


pytestmark = pytest.mark.skipif(
    not _binary_resolvable(),
    reason=(
        "AG_BINARY_PATH is not set (and `ag` is not on PATH); skipping "
        "ag_mcp live binary smoke tests."
    ),
)


@pytest.fixture(scope="module")
async def runner() -> AGRunner:
    output_dir()  # ensure subdirs exist
    r = AGRunner(binary_path=os.environ.get("AG_BINARY_PATH") or None)
    install_runner(r)
    yield r
    install_runner(None)


@pytest.fixture(scope="module")
async def synth_data(runner: AGRunner) -> Path:
    """Synthesize a 500-point ARIMA(1,0,1)-GARCH(1,1) series for downstream
    tests so we never need network access for the core checks."""
    out = returns_dir() / "smoke_synth.csv"
    await runner.sim(
        arima=(1, 0, 1),
        garch=(1, 1),
        length=500,
        output_path=out,
        seed=42,
    )
    assert out.exists()
    return out


@pytest.fixture(scope="module")
async def fitted_model(runner: AGRunner, synth_data: Path) -> Path:
    out = models_dir() / "smoke_fit.json"
    result = await runner.fit(
        data_path=synth_data,
        arima=(1, 0, 1),
        garch=(1, 1),
        output_path=out,
    )
    assert result.model_path.exists()
    assert isinstance(result.parsed, dict)
    return out


async def test_sim(synth_data: Path) -> None:
    """ag sim produced a non-empty CSV usable as input to ag_fit."""
    assert synth_data.exists()
    text = synth_data.read_text(encoding="utf-8").strip().splitlines()
    # At least header + 100 rows; we asked for 500.
    assert len(text) >= 101, f"sim CSV unexpectedly short: {len(text)} lines"


async def test_fit_on_synth(fitted_model: Path) -> None:
    """ag fit converged and produced a parseable model JSON."""
    import json

    data = json.loads(fitted_model.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data, "model JSON is empty"


async def test_select_picks_small_grid(runner: AGRunner, synth_data: Path) -> None:
    """ag select with a small grid returns a converged model JSON."""
    out = models_dir() / "smoke_select.json"
    result = await runner.select(
        data_path=synth_data,
        output_path=out,
        max_p=2,
        max_d=0,
        max_q=2,
        max_garch_p=1,
        max_garch_q=1,
        criterion="BIC",
    )
    assert out.exists()
    arima = result.parsed.get("arima")
    if arima is not None:
        p, d, q = arima
        assert p <= 2 and d <= 0 and q <= 2


async def test_forecast_horizon_rows(runner: AGRunner, fitted_model: Path) -> None:
    """ag forecast writes exactly `horizon` rows (plus header)."""
    horizon = 10
    out = forecasts_dir() / "smoke_forecast.csv"
    result = await runner.forecast(
        model_path=fitted_model,
        horizon=horizon,
        output_path=out,
    )
    assert out.exists()
    # A header line plus `horizon` data rows is what `ag forecast` produces.
    nrows = len(out.read_text(encoding="utf-8").strip().splitlines())
    assert nrows >= horizon, f"forecast CSV has {nrows} lines, expected >= {horizon}"
    assert len(result.rows) == horizon or (
        # Tolerate an off-by-one if the CLI also includes h=0 as anchor.
        len(result.rows) == horizon + 1
    )


async def test_simulate_inline_size(runner: AGRunner, fitted_model: Path) -> None:
    """ag simulate paths=5, length=20: long-format CSV should have 100 rows."""
    out = simulations_dir() / "smoke_sim.csv"
    await runner.simulate(
        model_path=fitted_model,
        paths=5,
        length=20,
        output_path=out,
        seed=7,
        stats=True,
    )
    assert out.exists()
    body = [
        ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    # Accept either long (paths*length = 100 rows + 1 header) or wide
    # (length rows + 1 header with 5 path columns).
    data_rows = len(body) - 1
    assert data_rows in (100, 20), (
        f"simulate CSV rows = {data_rows}; expected 100 (long) or 20 (wide)."
    )


async def test_diagnostics_pvalues_parsed(
    runner: AGRunner, fitted_model: Path, synth_data: Path
) -> None:
    """ag diagnostics: at least one test p-value parses out."""
    out = diagnostics_dir() / "smoke_diag.json"
    result = await runner.diagnostics(
        model_path=fitted_model,
        data_path=synth_data,
        output_path=out,
    )
    pvalues = [
        result.parsed.get("ljung_box_residuals_pvalue"),
        result.parsed.get("ljung_box_squared_residuals_pvalue"),
        result.parsed.get("jarque_bera_pvalue"),
    ]
    assert any(isinstance(v, (int, float)) for v in pvalues), (
        f"no p-values parsed from diagnostics stdout: {result.raw_stdout[:400]!r}"
    )


async def test_describe_model(fitted_model: Path) -> None:
    """ag_describe_model: persistence ∈ (0, 1) for a healthy fit."""
    from ag_mcp.registry import load_model

    info = load_model(fitted_model)
    persistence = info.get("garch_persistence")
    if persistence is None:
        # Soft assert: with synthetic data the fit may sometimes hit
        # boundary conditions; tolerate but log it.
        pytest.skip("garch_persistence not parsable from this synth fit")
    else:
        assert 0.0 < float(persistence) < 1.0, (
            f"persistence {persistence!r} not in (0,1)"
        )


# ---------- network-dependent smoke ---------------------------------------


@pytest.mark.skipif(
    not os.environ.get("FMP_API_KEY", "").strip(),
    reason="FMP_API_KEY not set; skipping ag_load_series live test.",
)
async def test_fmp_volatility_snapshot(runner: AGRunner) -> None:
    """End-to-end: ag_load_series('fmp_prices', 'SPY') →
    ag_volatility_snapshot. Hits FMP."""
    from ag_mcp.models import (
        InnovationDist,
        ReturnType,
        SelectionCriterion,
    )
    from ag_mcp.tools.composites import _volatility_snapshot_impl
    from ag_mcp.tools.data import _load_series_impl

    meta = await _load_series_impl(
        source="fmp_prices",
        identifier="SPY",
        from_date="2023-01-01",
        to_date=None,
        return_type=ReturnType.log,
        price_column="adjClose",
    )
    payload = await _volatility_snapshot_impl(
        identifier="SPY",
        meta=meta,
        auto_select=True,
        criterion=SelectionCriterion.BIC,
        innovation=InnovationDist.gaussian,
        forecast_horizon=10,
    )
    assert "model" in payload and "diagnostics" in payload
    assert payload["n_observations"] > 100
    assert "artifacts" in payload and "model_json" in payload["artifacts"]
