"""Unit tests for ag_mcp runner argv construction.

These tests mock the subprocess + filesystem layer entirely — no real `ag`
binary required. The point is to catch regressions in the translation from
the connector's (innovation, t_df) inputs to the CLI's actual flag shape,
which is the source of the bug fixed in this branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ag_mcp.runner import (
    DEFAULT_STUDENT_T_DF,
    AGRunner,
    _innovation_argv,
)


# ---------- pure helper ------------------------------------------------------


def test_innovation_argv_gaussian_emits_nothing() -> None:
    # The CLI has no --innovation flag; gaussian is the default-by-absence.
    assert _innovation_argv("gaussian", None) == []
    assert _innovation_argv("gaussian", 7.5) == []  # t_df is ignored


def test_innovation_argv_student_t_uses_t_dist_with_df() -> None:
    assert _innovation_argv("student_t", 4.0) == ["--t-dist", "4.0"]


def test_innovation_argv_student_t_defaults_df_when_missing() -> None:
    assert _innovation_argv("student_t", None) == [
        "--t-dist",
        str(DEFAULT_STUDENT_T_DF),
    ]


# ---------- runner argv assembly --------------------------------------------


class _FakeBinaryRunner(AGRunner):
    """AGRunner subclass that skips binary resolution + subprocess exec.

    Captures the assembled argv for assertion and (for `fit`) writes a
    trivial output file so the post-run existence check passes.
    """

    def __init__(self) -> None:
        super().__init__(binary_path="/fake/ag")
        self.captured_argv: list[str] | None = None

    def _resolve_binary(self) -> Path:  # type: ignore[override]
        return Path("/fake/ag")

    async def _run(self, argv, *, cmd):  # type: ignore[override]
        self.captured_argv = list(argv)
        # argv[-1] for sim/fit is `-o <path>` ... walk back to find it.
        try:
            out_idx = argv.index("-o") + 1
            Path(argv[out_idx]).parent.mkdir(parents=True, exist_ok=True)
            Path(argv[out_idx]).write_text("{}", encoding="utf-8")
        except (ValueError, IndexError):
            pass
        return ("", "")


@pytest.fixture
def fake_runner(tmp_path) -> _FakeBinaryRunner:
    return _FakeBinaryRunner()


async def test_fit_gaussian_argv_has_no_innovation_flags(
    fake_runner: _FakeBinaryRunner, tmp_path
) -> None:
    data = tmp_path / "in.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    out = tmp_path / "model.json"
    await fake_runner.fit(
        data_path=data,
        arima=(1, 0, 1),
        garch=(1, 1),
        output_path=out,
        innovation="gaussian",
    )
    argv = fake_runner.captured_argv or []
    # The bug: the connector used to append ['--innovation', 'gaussian'],
    # which the CLI rejects (no such flag). Guard against regression.
    assert "--innovation" not in argv
    assert "--t-dist" not in argv
    assert "--t-df" not in argv


async def test_fit_student_t_argv_uses_t_dist(
    fake_runner: _FakeBinaryRunner, tmp_path
) -> None:
    data = tmp_path / "in.csv"
    data.write_text("x\n1\n2\n", encoding="utf-8")
    out = tmp_path / "model.json"
    await fake_runner.fit(
        data_path=data,
        arima=(1, 0, 1),
        garch=(1, 1),
        output_path=out,
        innovation="student_t",
        t_df=3.5,
    )
    argv = fake_runner.captured_argv or []
    assert "--innovation" not in argv
    assert "--t-df" not in argv  # old (wrong) flag name
    assert argv[-2:] == ["--t-dist", "3.5"]


async def test_sim_gaussian_argv_has_no_innovation_flags(
    fake_runner: _FakeBinaryRunner, tmp_path
) -> None:
    out = tmp_path / "synth.csv"
    await fake_runner.sim(
        arima=(1, 0, 1),
        garch=(1, 1),
        length=100,
        output_path=out,
        innovation="gaussian",
    )
    argv = fake_runner.captured_argv or []
    assert "--innovation" not in argv
    assert "--t-dist" not in argv
    assert "--t-df" not in argv


async def test_sim_student_t_argv_uses_t_dist(
    fake_runner: _FakeBinaryRunner, tmp_path
) -> None:
    out = tmp_path / "synth.csv"
    await fake_runner.sim(
        arima=(1, 0, 1),
        garch=(1, 1),
        length=100,
        output_path=out,
        innovation="student_t",
        t_df=4.0,
    )
    argv = fake_runner.captured_argv or []
    assert "--innovation" not in argv
    assert "--t-df" not in argv
    assert argv[-2:] == ["--t-dist", "4.0"]
