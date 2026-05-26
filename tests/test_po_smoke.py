"""Live smoke tests for the po_mcp connector.

These tests shell out to the compiled `po` binary. They skip themselves
when ``PO_BINARY_PATH`` is unset (or the path doesn't exist), so a
no-secret CI run stays green.

Run with::

    PO_BINARY_PATH=/path/to/po PYTHONPATH=src pytest tests/test_po_smoke.py -q

The portopt-supplement block (HRP, ERC, walk-forward) additionally
``pytest.importorskip("portopt")`` so it auto-skips on installs that only
have the CLI binary.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from po_mcp.models import AssetDataInline, materialize_data
from po_mcp.output import data_dir, frontiers_dir, output_dir, results_dir
from po_mcp.runner import PORunner, install_runner


def _binary_resolvable() -> bool:
    env = os.environ.get("PO_BINARY_PATH", "").strip()
    if env and Path(env).expanduser().exists():
        return True
    return shutil.which("po") is not None


pytestmark = pytest.mark.skipif(
    not _binary_resolvable(),
    reason=(
        "PO_BINARY_PATH is not set (and `po` is not on PATH); skipping "
        "po_mcp live binary smoke tests."
    ),
)


@pytest.fixture(scope="module")
async def runner() -> PORunner:
    output_dir()  # ensure subdirs exist
    r = PORunner(binary_path=os.environ.get("PO_BINARY_PATH") or None)
    install_runner(r)
    yield r
    install_runner(None)


@pytest.fixture(scope="module")
def three_asset_data(tmp_path_factory) -> Path:
    """A tiny 3-asset assets.json suitable for every CLI subcommand."""
    inline = AssetDataInline.model_validate(
        {
            "assets": [
                {"ticker": "A", "expected_return": 0.10, "sector": "Tech"},
                {"ticker": "B", "expected_return": 0.08, "sector": "Tech"},
                {"ticker": "C", "expected_return": 0.06, "sector": "Energy"},
            ],
            "covariance": [
                [0.04, 0.01, 0.005],
                [0.01, 0.09, 0.005],
                [0.005, 0.005, 0.025],
            ],
            "market_weights": [0.4, 0.4, 0.2],
            "benchmark_weights": [0.4, 0.4, 0.2],
            "risk_free_rate": 0.03,
        }
    )
    return materialize_data(inline)


# ---------- CLI subcommands -----------------------------------------------


async def test_mvo_returns_weights_summing_to_one(runner, three_asset_data) -> None:
    out = results_dir() / "smoke_mvo.json"
    result = await runner.mvo(data_path=three_asset_data, output_path=out)
    assert result.weights, "weights dict should be populated"
    assert abs(sum(result.weights.values()) - 1.0) < 1e-4


async def test_min_variance_writes_result_json(runner, three_asset_data) -> None:
    out = results_dir() / "smoke_minvar.json"
    result = await runner.min_variance(data_path=three_asset_data, output_path=out)
    assert out.exists()
    assert isinstance(result.metrics.get("volatility"), (int, float))


async def test_max_sharpe_writes_result_json(runner, three_asset_data) -> None:
    out = results_dir() / "smoke_maxshp.json"
    result = await runner.max_sharpe(data_path=three_asset_data, output_path=out)
    assert out.exists()
    assert result.weights


async def test_frontier_csv_has_multiple_points(runner, three_asset_data) -> None:
    out = frontiers_dir() / "smoke_front.csv"
    result = await runner.frontier(data_path=three_asset_data, output_path=out)
    assert out.exists()
    assert len(result.rows) >= 5, f"expected ≥5 frontier points, got {len(result.rows)}"


async def test_target_vol_runs(runner, three_asset_data) -> None:
    out = results_dir() / "smoke_tv.json"
    result = await runner.target_vol(
        data_path=three_asset_data, target=0.15, output_path=out
    )
    assert result.weights


# ---------- portopt-supplement tools --------------------------------------


def test_hrp_weights_sum_to_one() -> None:
    pytest.importorskip("portopt")
    from po_mcp import pyengine

    cov = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.005],
        [0.005, 0.005, 0.025],
    ]
    result = pyengine.hierarchical_risk_parity(["A", "B", "C"], cov)
    total = sum(result["weights"].values())
    assert abs(total - 1.0) < 1e-4


def test_equal_risk_contribution_balances_contributions() -> None:
    pytest.importorskip("portopt")
    from po_mcp import pyengine

    cov = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.005],
        [0.005, 0.005, 0.025],
    ]
    result = pyengine.equal_risk_contribution(["A", "B", "C"], cov)
    rc = list(result["risk_contributions"].values())
    # All risk contributions should be close to 1/n = 1/3
    target = 1.0 / 3.0
    for v in rc:
        assert abs(v - target) < 0.05, f"ERC contribution {v} != {target}"


def test_summarize_portfolio_computes_basic_metrics() -> None:
    pytest.importorskip("portopt")
    from po_mcp import pyengine

    cov = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.005],
        [0.005, 0.005, 0.025],
    ]
    weights = {"A": 0.4, "B": 0.4, "C": 0.2}
    result = pyengine.summarize_portfolio(
        weights, cov,
        expected_returns={"A": 0.10, "B": 0.08, "C": 0.06},
        risk_free_rate=0.03,
        tickers=["A", "B", "C"],
    )
    metrics = result["metrics"]
    assert metrics["volatility"] > 0
    assert "sharpe_ratio" in metrics
    assert "diversification_ratio" in metrics
    assert "effective_n" in metrics


def test_estimate_from_returns_writes_assets_dict(tmp_path) -> None:
    pytest.importorskip("portopt")
    import numpy as np

    from po_mcp import pyengine

    rng = np.random.default_rng(42)
    R = rng.normal(0.0005, 0.012, size=(252, 4))
    # First column is a date label
    csv_path = tmp_path / "returns.csv"
    with csv_path.open("w") as fp:
        fp.write("date,A,B,C,D\n")
        for i, row in enumerate(R):
            fp.write(f"2023-01-{i+1:02d}," + ",".join(f"{v:.6f}" for v in row) + "\n")
    out = pyengine.estimate_from_returns(
        csv_path, periods_per_year=252, shrinkage="ledoit-wolf"
    )
    assert "assets" in out
    assert "covariance" in out
    assert len(out["assets"]) == 4
