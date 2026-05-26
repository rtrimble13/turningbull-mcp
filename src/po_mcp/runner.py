"""Async subprocess wrapper around the `po` CLI.

A single :class:`PORunner` exposes one method per `po` subcommand:
``mvo``, ``frontier``, ``bl``, ``bl_frontier``, ``min_variance``,
``max_sharpe``, ``target_vol``, ``target_return``, ``report``.

Each method:

1. Resolves ``$PO_BINARY_PATH`` (falling back to ``shutil.which("po")``),
   cached after first lookup.
2. Builds argv from typed keyword arguments — see ``_common_flags`` for
   the shared optimizer kwargs and each method's signature for any
   subcommand-specific flags.
3. Forces ``-f json`` (or ``-f csv`` for frontiers) so output is always
   machine-readable; never relies on free-text console output.
4. Runs ``asyncio.create_subprocess_exec`` with stdout/stderr captured
   and a configurable wall-clock timeout from ``$PO_SUBPROCESS_TIMEOUT``
   (default 600s).
5. Loads the written artifact (JSON / CSV) and returns a small dataclass
   containing weights, metrics, diagnostics, the artifact path, the raw
   stdout/stderr, and the argv list.
6. Maps non-zero exit codes to :class:`POError`; on timeout, raises
   :class:`POError` with a hint to reduce work.

The runner holds no mutable state beyond the cached binary path; methods
are safe to call concurrently.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import POError, binary_not_found_message, map_returncode, timeout_message
from .interpretation import (
    extract_diagnostics,
    extract_metrics,
    extract_weights,
    frontier_summary,
    load_result_json,
    read_csv_rows,
)

DEFAULT_TIMEOUT_SECONDS = 600.0


# ---------- result dataclasses -------------------------------------------


@dataclass
class OptimizationResult:
    """Single-portfolio result from `po mvo`/`min-variance`/`max-sharpe`/
    ``target-*``/``bl``. ``result_json_path`` is the file `po` wrote.
    """

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    result_json_path: Path
    weights: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class FrontierResult:
    """Frontier result from `po frontier`/`bl-frontier`. CSV columns are
    typically ``risk_aversion, volatility, expected_return, sharpe`` plus
    a column per asset.
    """

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    frontier_csv_path: Path
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportResult:
    """`po report` result. Writes an HTML + executed notebook to the
    output dir."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    output_dir: Path
    html_path: Path | None = None
    notebook_path: Path | None = None


# ---------- runner --------------------------------------------------------


class PORunner:
    """Async wrapper around the `po` binary.

    All methods are coroutines and safe to call concurrently. Set the
    binary path via ``$PO_BINARY_PATH`` or place ``po`` on ``$PATH``;
    override the timeout with ``$PO_SUBPROCESS_TIMEOUT`` (seconds).
    """

    def __init__(self, binary_path: str | Path | None = None) -> None:
        self._binary_path: Path | None = (
            Path(binary_path).expanduser().resolve() if binary_path else None
        )

    # ------------ binary resolution ------------------------------------

    def _resolve_binary(self) -> Path:
        if self._binary_path is not None and self._binary_path.exists():
            return self._binary_path
        env_path = os.environ.get("PO_BINARY_PATH", "").strip()
        if env_path:
            p = Path(env_path).expanduser()
            if not p.exists():
                raise POError(
                    f"PO_BINARY_PATH is set to {env_path!r} but no such "
                    "file exists. " + binary_not_found_message()
                )
            self._binary_path = p.resolve()
            return self._binary_path
        which = shutil.which("po")
        if which:
            self._binary_path = Path(which).resolve()
            return self._binary_path
        raise POError(binary_not_found_message())

    @staticmethod
    def _timeout() -> float:
        raw = os.environ.get("PO_SUBPROCESS_TIMEOUT", "").strip()
        if not raw:
            return DEFAULT_TIMEOUT_SECONDS
        try:
            return max(float(raw), 1.0)
        except ValueError:
            return DEFAULT_TIMEOUT_SECONDS

    # ------------ low-level subprocess runner --------------------------

    async def _run(self, argv: list[str], *, cmd: str) -> tuple[str, str]:
        """Run argv and return ``(stdout, stderr)`` text on success.

        Raises :class:`POError` on non-zero exit or timeout.
        """
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout = self._timeout()
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            finally:
                await proc.wait()
            raise POError(timeout_message(cmd, timeout)) from exc

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        rc = proc.returncode if proc.returncode is not None else -1
        if rc != 0:
            raise map_returncode(rc, stderr, cmd=cmd)
        return stdout, stderr

    # ------------ argv helpers -----------------------------------------

    @staticmethod
    def _common_flags(
        *,
        total_capital: float | None = None,
        returns: bool = False,
        periods_per_year: float | None = None,
        shrinkage: str | None = None,
        shrinkage_delta: float | None = None,
        risk_aversion: float | None = None,
        risk_free_rate: float | None = None,
        turnover_penalty: float | None = None,
        budget: float | None = None,
        show_zero: bool = False,
        explain: bool = False,
        log_level: str | None = None,
        ascii_only: bool = False,
    ) -> list[str]:
        """Translate shared optimizer kwargs into a flat argv list.

        Each option is only emitted when set; flags only when ``True``.
        """
        argv: list[str] = []
        if total_capital is not None:
            argv += ["--total-capital", _fmt(total_capital)]
        if returns:
            argv.append("--returns")
        if periods_per_year is not None:
            argv += ["--periods-per-year", _fmt(periods_per_year)]
        if shrinkage is not None:
            argv += ["--shrinkage", str(shrinkage)]
        if shrinkage_delta is not None:
            argv += ["--shrinkage-delta", _fmt(shrinkage_delta)]
        if risk_aversion is not None:
            argv += ["--risk-aversion", _fmt(risk_aversion)]
        if risk_free_rate is not None:
            argv += ["--risk-free-rate", _fmt(risk_free_rate)]
        if turnover_penalty is not None:
            argv += ["--turnover-penalty", _fmt(turnover_penalty)]
        if budget is not None:
            argv += ["--budget", _fmt(budget)]
        if show_zero:
            argv.append("--show-zero")
        if explain:
            argv.append("--explain")
        if log_level:
            argv += ["--log-level", str(log_level)]
        if ascii_only:
            argv.append("--ascii")
        return argv

    def _argv_base(
        self,
        subcmd: str,
        *,
        data_path: Path,
        params_path: Path | None,
        output_path: Path,
        output_format: str,
    ) -> list[str]:
        """Common ``[binary, subcmd, -d, -p?, -o, -f]`` argv prefix."""
        binary = self._resolve_binary()
        argv = [
            str(binary),
            subcmd,
            "-d",
            str(data_path),
        ]
        if params_path is not None:
            argv += ["-p", str(params_path)]
        argv += [
            "-o",
            str(output_path),
            "-f",
            output_format,
        ]
        return argv

    # ------------ result-loading helper --------------------------------

    @staticmethod
    def _load_optimization(
        path: Path,
        argv: list[str],
        stdout: str,
        stderr: str,
    ) -> OptimizationResult:
        if not path.exists():
            raise POError(
                f"`po` reported success but {path} was not written. "
                f"argv: {argv!r}"
            )
        raw_json = load_result_json(path)
        return OptimizationResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            result_json_path=path,
            weights=extract_weights(raw_json),
            metrics=extract_metrics(raw_json),
            diagnostics=extract_diagnostics(raw_json),
            raw_json=raw_json,
        )

    @staticmethod
    def _load_frontier(
        path: Path,
        argv: list[str],
        stdout: str,
        stderr: str,
    ) -> FrontierResult:
        if not path.exists():
            raise POError(
                f"`po` reported success but {path} was not written. "
                f"argv: {argv!r}"
            )
        rows = read_csv_rows(path)
        return FrontierResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            frontier_csv_path=path,
            rows=rows,
            summary=frontier_summary(rows),
        )

    # ------------ subcommand methods -----------------------------------

    async def mvo(
        self,
        *,
        data_path: Path,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> OptimizationResult:
        """`po mvo -d ... [-p ...] -o ... -f json [common flags]`."""
        argv = self._argv_base(
            "mvo",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="mvo")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def frontier(
        self,
        *,
        data_path: Path,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> FrontierResult:
        """`po frontier ... -f csv` — efficient frontier."""
        argv = self._argv_base(
            "frontier",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="csv",
        )
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="frontier")
        return self._load_frontier(output_path, argv, stdout, stderr)

    async def bl(
        self,
        *,
        data_path: Path,
        params_path: Path,
        output_path: Path,
        show_model: bool = False,
        **flags: Any,
    ) -> OptimizationResult:
        """`po bl -d ... -p ... -o ... -f json [--show-model]`."""
        argv = self._argv_base(
            "bl",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += self._common_flags(**flags)
        if show_model:
            argv.append("--show-model")
        stdout, stderr = await self._run(argv, cmd="bl")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def bl_frontier(
        self,
        *,
        data_path: Path,
        params_path: Path,
        output_path: Path,
        **flags: Any,
    ) -> FrontierResult:
        """`po bl-frontier ... -f csv`."""
        argv = self._argv_base(
            "bl-frontier",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="csv",
        )
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="bl-frontier")
        return self._load_frontier(output_path, argv, stdout, stderr)

    async def min_variance(
        self,
        *,
        data_path: Path,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> OptimizationResult:
        """`po min-variance ...`."""
        argv = self._argv_base(
            "min-variance",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="min-variance")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def max_sharpe(
        self,
        *,
        data_path: Path,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> OptimizationResult:
        """`po max-sharpe ...`."""
        argv = self._argv_base(
            "max-sharpe",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="max-sharpe")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def target_vol(
        self,
        *,
        data_path: Path,
        target: float,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> OptimizationResult:
        """`po target-vol --target X ...`."""
        if target <= 0:
            raise POError(f"target volatility must be > 0; got {target}")
        argv = self._argv_base(
            "target-vol",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += ["--target", _fmt(target)]
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="target-vol")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def target_return(
        self,
        *,
        data_path: Path,
        target: float,
        output_path: Path,
        params_path: Path | None = None,
        **flags: Any,
    ) -> OptimizationResult:
        """`po target-return --target X ...`."""
        argv = self._argv_base(
            "target-return",
            data_path=data_path,
            params_path=params_path,
            output_path=output_path,
            output_format="json",
        )
        argv += ["--target", _fmt(target)]
        argv += self._common_flags(**flags)
        stdout, stderr = await self._run(argv, cmd="target-return")
        return self._load_optimization(output_path, argv, stdout, stderr)

    async def report(
        self,
        *,
        data_path: Path,
        output_dir: Path,
        params_path: Path | None = None,
        method: Literal["mvo", "bl", "both"] = "both",
        notebook_template: Path | None = None,
    ) -> ReportResult:
        """`po report -d ... -p ... -o <dir> -m mvo|bl|both`."""
        binary = self._resolve_binary()
        output_dir.mkdir(parents=True, exist_ok=True)
        argv: list[str] = [
            str(binary),
            "report",
            "-d",
            str(data_path),
        ]
        if params_path is not None:
            argv += ["-p", str(params_path)]
        argv += ["-o", str(output_dir), "-m", method]
        if notebook_template is not None:
            argv += ["-n", str(notebook_template)]
        stdout, stderr = await self._run(argv, cmd="report")
        # `po report` writes a notebook + HTML; find whatever it produced.
        html = _first_match(output_dir, "*.html")
        nb = _first_match(output_dir, "*.ipynb")
        return ReportResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            output_dir=output_dir,
            html_path=html,
            notebook_path=nb,
        )


# ---------- helpers -------------------------------------------------------


def _fmt(value: float) -> str:
    """Render a float without scientific notation for CLI argv."""
    if isinstance(value, int) or value == int(value):
        return str(int(value)) if abs(value) < 1e15 else repr(value)
    return repr(value)


def _first_match(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    return matches[0] if matches else None


# ---------- singleton -----------------------------------------------------

_singleton: PORunner | None = None


def install_runner(runner: PORunner | None) -> None:
    """Register the runner for tools to retrieve via :func:`get_runner`."""
    global _singleton
    _singleton = runner


def get_runner() -> PORunner:
    if _singleton is None:
        raise POError(
            "PORunner is not initialized. The server's lifespan failed to start."
        )
    return _singleton
