"""Unit tests for po_mcp runner argv construction and data materialization.

These tests mock the subprocess + filesystem layer entirely — no real
`po` binary or `portopt` Python build required. They cover:

- argv assembly for each `po` subcommand (correct subcommand name, -d/-p/-o,
  -f json|csv routing, --target / --show-model flags, common-flag pairing).
- Inline-JSON data materialization to ``$PO_OUTPUT_DIR/tmp/`` is
  content-addressed (identical payloads dedup; mutation produces a new
  file) and idempotent across runs.
- DataPathInput passes through unchanged.
- po_validate_data rejects non-PSD covariance and ticker/dimension
  mismatches.
- pyengine raises an actionable error when portopt can't be imported.
- The runner singleton install/get round-trips.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from po_mcp.models import (
    AssetDataInline,
    BlackLittermanParams,
    DataPathInput,
    OptimizationParams,
    Shrinkage,
    materialize_data,
    materialize_params,
)
from po_mcp.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    OptimizationResult,
    PORunner,
    get_runner,
    install_runner,
)
from po_mcp.errors import POError


# ---------- fake runner: captures argv, writes stub output -------------------


class _FakeBinaryRunner(PORunner):
    """PORunner subclass that skips binary resolution + subprocess exec.

    Captures the assembled argv for assertion and writes a trivial JSON or
    CSV output file so the post-run load check passes.
    """

    def __init__(self) -> None:
        super().__init__(binary_path="/fake/po")
        self.captured_argv: list[str] | None = None

    def _resolve_binary(self) -> Path:  # type: ignore[override]
        return Path("/fake/po")

    async def _run(self, argv, *, cmd):  # type: ignore[override]
        self.captured_argv = list(argv)
        try:
            out_idx = argv.index("-o") + 1
        except ValueError:
            return ("", "")
        out_path = Path(argv[out_idx])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Pick a stub payload based on -f
        fmt = "json"
        if "-f" in argv:
            fmt = argv[argv.index("-f") + 1]
        if fmt == "csv":
            out_path.write_text(
                "risk_aversion,volatility,expected_return,sharpe\n"
                "1.0,0.10,0.08,0.4\n"
                "2.0,0.12,0.10,0.5\n"
                "3.0,0.15,0.12,0.45\n",
                encoding="utf-8",
            )
        else:
            out_path.write_text(
                json.dumps(
                    {
                        "weights": {"A": 0.4, "B": 0.6},
                        "metrics": {
                            "expected_return": 0.10,
                            "volatility": 0.12,
                            "sharpe_ratio": 0.5,
                        },
                        "diagnostics": {"solver_status": "converged"},
                    }
                ),
                encoding="utf-8",
            )
        return ("", "")


@pytest.fixture
def fake_runner() -> _FakeBinaryRunner:
    return _FakeBinaryRunner()


# ---------- shared sample inputs --------------------------------------------


@pytest.fixture
def assets_inline() -> AssetDataInline:
    return AssetDataInline.model_validate(
        {
            "assets": [{"ticker": "A"}, {"ticker": "B"}],
            "covariance": [[0.04, 0.01], [0.01, 0.09]],
            "risk_free_rate": 0.02,
        }
    )


@pytest.fixture
def written_data_path(tmp_path, assets_inline) -> Path:
    """Write the inline data to a real file under tmp_path."""
    p = tmp_path / "assets.json"
    p.write_text(json.dumps(assets_inline.model_dump(exclude={"kind"})), encoding="utf-8")
    return p


# ---------- argv assembly: every subcommand ---------------------------------


async def test_mvo_argv_basic(fake_runner, tmp_path, written_data_path) -> None:
    out = tmp_path / "results" / "mvo.json"
    result = await fake_runner.mvo(data_path=written_data_path, output_path=out)
    argv = fake_runner.captured_argv or []
    assert argv[0] == "/fake/po"
    assert argv[1] == "mvo"
    assert "-d" in argv and "-o" in argv and "-f" in argv
    assert argv[argv.index("-f") + 1] == "json"
    assert "-p" not in argv  # no params provided
    assert isinstance(result, OptimizationResult)
    assert result.weights == {"A": 0.4, "B": 0.6}


async def test_mvo_argv_with_params(fake_runner, tmp_path, written_data_path) -> None:
    params_path = tmp_path / "params.json"
    params_path.write_text("{}", encoding="utf-8")
    out = tmp_path / "results" / "mvo.json"
    await fake_runner.mvo(
        data_path=written_data_path,
        output_path=out,
        params_path=params_path,
    )
    argv = fake_runner.captured_argv or []
    assert "-p" in argv
    assert argv[argv.index("-p") + 1] == str(params_path)


async def test_frontier_forces_f_csv(fake_runner, tmp_path, written_data_path) -> None:
    out = tmp_path / "frontiers" / "f.csv"
    result = await fake_runner.frontier(data_path=written_data_path, output_path=out)
    argv = fake_runner.captured_argv or []
    assert argv[1] == "frontier"
    assert argv[argv.index("-f") + 1] == "csv"
    assert result.rows  # stub CSV had 3 rows
    assert result.summary.get("n_points") == 3


async def test_target_vol_emits_target_flag(
    fake_runner, tmp_path, written_data_path
) -> None:
    out = tmp_path / "results" / "tv.json"
    await fake_runner.target_vol(
        data_path=written_data_path, target=0.15, output_path=out
    )
    argv = fake_runner.captured_argv or []
    assert argv[1] == "target-vol"
    assert "--target" in argv
    assert argv[argv.index("--target") + 1] == "0.15"


async def test_target_vol_rejects_non_positive(
    fake_runner, tmp_path, written_data_path
) -> None:
    out = tmp_path / "results" / "tv.json"
    with pytest.raises(POError, match="target volatility"):
        await fake_runner.target_vol(
            data_path=written_data_path, target=0.0, output_path=out
        )


async def test_target_return_emits_target_flag(
    fake_runner, tmp_path, written_data_path
) -> None:
    out = tmp_path / "results" / "tr.json"
    await fake_runner.target_return(
        data_path=written_data_path, target=0.08, output_path=out
    )
    argv = fake_runner.captured_argv or []
    assert argv[1] == "target-return"
    assert "--target" in argv


async def test_min_variance_and_max_sharpe_subcommand_names(
    fake_runner, tmp_path, written_data_path
) -> None:
    out_mv = tmp_path / "results" / "mv.json"
    await fake_runner.min_variance(data_path=written_data_path, output_path=out_mv)
    assert (fake_runner.captured_argv or [])[1] == "min-variance"
    out_ms = tmp_path / "results" / "ms.json"
    await fake_runner.max_sharpe(data_path=written_data_path, output_path=out_ms)
    assert (fake_runner.captured_argv or [])[1] == "max-sharpe"


async def test_bl_passes_show_model_flag(
    fake_runner, tmp_path, written_data_path
) -> None:
    params_path = tmp_path / "bl_params.json"
    params_path.write_text("{}", encoding="utf-8")
    out = tmp_path / "results" / "bl.json"
    await fake_runner.bl(
        data_path=written_data_path,
        params_path=params_path,
        output_path=out,
        show_model=True,
    )
    argv = fake_runner.captured_argv or []
    assert argv[1] == "bl"
    assert "--show-model" in argv


async def test_bl_frontier_forces_csv(
    fake_runner, tmp_path, written_data_path
) -> None:
    params_path = tmp_path / "bl_params.json"
    params_path.write_text("{}", encoding="utf-8")
    out = tmp_path / "frontiers" / "blf.csv"
    await fake_runner.bl_frontier(
        data_path=written_data_path,
        params_path=params_path,
        output_path=out,
    )
    argv = fake_runner.captured_argv or []
    assert argv[1] == "bl-frontier"
    assert argv[argv.index("-f") + 1] == "csv"


# ---------- common flags ----------------------------------------------------


def test_common_flags_emits_each_flag_when_set() -> None:
    flags = PORunner._common_flags(
        total_capital=1_000_000.0,
        returns=True,
        periods_per_year=252,
        shrinkage="ledoit-wolf",
        shrinkage_delta=0.3,
        risk_aversion=2.5,
        risk_free_rate=0.04,
        turnover_penalty=0.01,
        budget=1.0,
        show_zero=True,
        explain=True,
        log_level="warn",
        ascii_only=True,
    )
    assert "--total-capital" in flags
    assert "--returns" in flags
    assert "--periods-per-year" in flags
    assert "--shrinkage" in flags
    assert "ledoit-wolf" in flags
    assert "--shrinkage-delta" in flags
    assert "--risk-aversion" in flags
    assert "--risk-free-rate" in flags
    assert "--turnover-penalty" in flags
    assert "--budget" in flags
    assert "--show-zero" in flags
    assert "--explain" in flags
    assert "--log-level" in flags
    assert "warn" in flags
    assert "--ascii" in flags


def test_common_flags_omits_unset_kwargs() -> None:
    assert PORunner._common_flags() == []


# ---------- data materialization -------------------------------------------


def test_inline_data_materializes_to_content_addressed_path(
    tmp_path, monkeypatch, assets_inline
) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    path_a = materialize_data(assets_inline)
    path_b = materialize_data(assets_inline)
    assert path_a == path_b, "identical payloads must dedup to the same file"
    assert path_a.exists()
    assert path_a.parent.name == "tmp"
    assert path_a.name.startswith("data_") and path_a.suffix == ".json"


def test_inline_data_mutation_changes_hashed_filename(
    tmp_path, monkeypatch, assets_inline
) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    path_a = materialize_data(assets_inline)
    # Mutate covariance → different hash
    mutated = AssetDataInline.model_validate(
        {
            **assets_inline.model_dump(exclude={"kind"}),
            "covariance": [[0.05, 0.01], [0.01, 0.09]],
        }
    )
    path_b = materialize_data(mutated)
    assert path_a != path_b


def test_datapath_input_passes_through_unchanged(
    tmp_path, monkeypatch, written_data_path
) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    p = materialize_data(DataPathInput(path=written_data_path))
    assert p == written_data_path.resolve()


def test_inline_dict_with_kind_inline_routes_correctly(
    tmp_path, monkeypatch, assets_inline
) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    plain = assets_inline.model_dump(exclude={"kind"})
    p = materialize_data({**plain, "kind": "inline"})
    assert p.exists() and p.parent.name == "tmp"


def test_materialize_params_writes_mvo_wrapper(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    params = OptimizationParams(risk_aversion=2.0, budget=1.0)
    path = materialize_params(params, kind="mvo")
    assert path is not None
    content = json.loads(path.read_text(encoding="utf-8"))
    assert "mvo" in content
    assert content["mvo"]["risk_aversion"] == 2.0


def test_materialize_params_writes_bl_wrapper(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PO_OUTPUT_DIR", str(tmp_path / "po_output"))
    bl = BlackLittermanParams.model_validate(
        {
            "tau": 0.05,
            "views": [
                {
                    "pick_vector": {"A": 1.0, "B": -1.0},
                    "expected_return": 0.03,
                    "confidence": 0.7,
                }
            ],
        }
    )
    path = materialize_params(bl, kind="bl")
    assert path is not None
    content = json.loads(path.read_text(encoding="utf-8"))
    assert "black_litterman" in content
    assert content["black_litterman"]["views"][0]["expected_return"] == 0.03


def test_materialize_params_returns_none_for_none() -> None:
    assert materialize_params(None, kind="mvo") is None


# ---------- po_validate_data tool logic ------------------------------------


def test_validate_data_accepts_clean_input() -> None:
    from po_mcp.tools.data import _psd_issues

    issues = _psd_issues([[0.04, 0.01], [0.01, 0.09]], ridge=1e-10)
    assert issues == []


def test_validate_data_rejects_non_symmetric_sigma() -> None:
    from po_mcp.tools.data import _psd_issues

    issues = _psd_issues([[0.04, 0.01], [0.02, 0.09]], ridge=1e-10)
    assert any("symmetric" in i for i in issues)


def test_validate_data_rejects_non_psd() -> None:
    from po_mcp.tools.data import _psd_issues

    # Negative eigenvalue: not PSD
    issues = _psd_issues([[1.0, 2.0], [2.0, 1.0]], ridge=0.0)
    assert any("positive semi-definite" in i for i in issues)


def test_validate_data_reports_nonnumeric_covariance_entries() -> None:
    from po_mcp.tools.data import _psd_issues

    issues = _psd_issues([[0.04, "bad"], [0.01, 0.09]], ridge=1e-10)  # type: ignore[list-item]
    assert any("non-numeric or ragged" in i for i in issues)


# ---------- pyengine lazy-import ------------------------------------------


def test_pyengine_lazy_import_raises_actionable_error(monkeypatch) -> None:
    from po_mcp import pyengine as pe

    monkeypatch.setattr(pe, "_portopt_mod", None)
    # Block portopt import even if it's installed in the env.
    monkeypatch.setitem(sys.modules, "portopt", None)
    with pytest.raises(POError, match="portopt Python module could not be imported"):
        pe.equal_risk_contribution(["A", "B"], [[0.04, 0.01], [0.01, 0.09]])


# ---------- runner singleton -----------------------------------------------


def test_install_and_get_runner_round_trip() -> None:
    runner = PORunner(binary_path="/tmp/fake-po")
    install_runner(runner)
    try:
        assert get_runner() is runner
    finally:
        install_runner(None)


def test_get_runner_raises_when_uninitialized() -> None:
    install_runner(None)
    with pytest.raises(POError, match="not initialized"):
        get_runner()


# ---------- timeout env var ------------------------------------------------


def test_timeout_default_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("PO_SUBPROCESS_TIMEOUT", raising=False)
    assert PORunner._timeout() == DEFAULT_TIMEOUT_SECONDS


def test_timeout_respects_env(monkeypatch) -> None:
    monkeypatch.setenv("PO_SUBPROCESS_TIMEOUT", "30")
    assert PORunner._timeout() == 30.0


def test_timeout_floor(monkeypatch) -> None:
    monkeypatch.setenv("PO_SUBPROCESS_TIMEOUT", "0")
    assert PORunner._timeout() >= 1.0


def test_timeout_falls_back_on_invalid(monkeypatch) -> None:
    monkeypatch.setenv("PO_SUBPROCESS_TIMEOUT", "not-a-number")
    assert PORunner._timeout() == DEFAULT_TIMEOUT_SECONDS


# ---------- binary resolution ----------------------------------------------


def test_resolve_binary_raises_when_nothing_found(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PO_BINARY_PATH", raising=False)
    # Make sure `po` isn't on PATH
    monkeypatch.setenv("PATH", str(tmp_path))
    runner = PORunner(binary_path=None)
    with pytest.raises(POError, match="binary not found"):
        runner._resolve_binary()


def test_resolve_binary_uses_env_path(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "po"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PO_BINARY_PATH", str(fake))
    runner = PORunner(binary_path=None)
    assert runner._resolve_binary() == fake.resolve()


def test_resolve_binary_errors_when_env_path_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PO_BINARY_PATH", str(tmp_path / "nonexistent" / "po"))
    runner = PORunner(binary_path=None)
    with pytest.raises(POError, match="no such file"):
        runner._resolve_binary()
