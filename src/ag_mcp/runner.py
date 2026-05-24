"""Async subprocess wrapper around the `ag` CLI.

A single :class:`AGRunner` exposes one method per `ag` subcommand. Each
method:

1. Resolves ``$AG_BINARY_PATH`` (falling back to ``shutil.which("ag")``),
   cached after first lookup.
2. Builds argv from typed keyword arguments — see each method's docstring
   for the corresponding CLI flag mapping.
3. Runs ``asyncio.create_subprocess_exec`` with stdout/stderr captured
   and a configurable wall-clock timeout from ``$AG_SUBPROCESS_TIMEOUT``
   (default 600s).
4. Returns a small dataclass containing the *raw* stdout (the CLI's
   analyst-readable report — never thrown away) plus any structured
   fields parsed from stdout and any written JSON artifact, so callers
   never have to scrape free text themselves.
5. Maps non-zero exit codes to :class:`AGError`; on timeout, raises
   :class:`AGError` with a hint to reduce work.

The runner holds no mutable state beyond the cached binary path; methods
are safe to call concurrently.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import AGError, binary_not_found_message, map_returncode, timeout_message
from .interpretation import (
    parse_diagnostics_stdout,
    parse_fit_stdout,
    parse_model_json,
    parse_simulate_stats_stdout,
)

DEFAULT_TIMEOUT_SECONDS = 600.0

# The CLI selects the innovation distribution by the presence/absence of
# `--t-dist <df>`: omit it for Gaussian, pass it (with a positive df) for
# Student-t. There is no `--innovation` flag. Default df=5.0 matches the
# `student_t_df5` scenario in `tools/composites.py`.
DEFAULT_STUDENT_T_DF = 5.0


def _innovation_argv(
    innovation: Literal["gaussian", "student_t"], t_df: float | None
) -> list[str]:
    """Translate (innovation, t_df) into the CLI's argv form."""
    if innovation == "student_t":
        df = float(t_df) if t_df is not None else DEFAULT_STUDENT_T_DF
        return ["--t-dist", str(df)]
    return []


# ---------- result dataclasses -------------------------------------------


@dataclass
class FitResult:
    """`ag fit` result. ``model_path`` is the written JSON; ``parsed`` is the
    combined structured view (JSON file + stdout-scraped fit-only fields)."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    model_path: Path
    parsed: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectResult:
    """`ag select` result. ``model_path`` is the JSON of the chosen model.

    ``top_k`` (if requested) is a list of dicts the CLI prints for the top
    candidates; we parse what we can but the raw text is the ground truth.
    """

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    model_path: Path
    parsed: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastResult:
    """`ag forecast` result. CSV columns are typically ``horizon, mean,
    variance, lower_95, upper_95``; we read them as-is from the file."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    forecast_csv: Path
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulateResult:
    """`ag simulate` result. CSV is long-format ``path, t, value`` (or wide
    paths x time); we expose the file path and the parsed summary stats."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    simulation_csv: Path
    parsed_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticsResult:
    """`ag diagnostics` result. JSON file (when written) plus stdout parse."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    diagnostics_path: Path | None
    parsed: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimResult:
    """`ag sim` result. Writes a single-column CSV of synthetic returns."""

    raw_stdout: str
    raw_stderr: str
    argv: list[str]
    data_csv: Path


# ---------- runner --------------------------------------------------------


class AGRunner:
    """Async wrapper around the `ag` binary.

    All methods are coroutines and safe to call concurrently. Set the
    binary path via ``$AG_BINARY_PATH`` or place ``ag`` on ``$PATH``;
    override the timeout with ``$AG_SUBPROCESS_TIMEOUT`` (seconds).
    """

    def __init__(self, binary_path: str | Path | None = None) -> None:
        self._binary_path: Path | None = (
            Path(binary_path).expanduser().resolve() if binary_path else None
        )

    # ------------ binary resolution ------------------------------------

    def _resolve_binary(self) -> Path:
        if self._binary_path is not None and self._binary_path.exists():
            return self._binary_path
        env_path = os.environ.get("AG_BINARY_PATH", "").strip()
        if env_path:
            p = Path(env_path).expanduser()
            if not p.exists():
                raise AGError(
                    f"AG_BINARY_PATH is set to {env_path!r} but no such "
                    "file exists. " + binary_not_found_message()
                )
            self._binary_path = p.resolve()
            return self._binary_path
        which = shutil.which("ag")
        if which:
            self._binary_path = Path(which).resolve()
            return self._binary_path
        raise AGError(binary_not_found_message())

    @staticmethod
    def _timeout() -> float:
        raw = os.environ.get("AG_SUBPROCESS_TIMEOUT", "").strip()
        if not raw:
            return DEFAULT_TIMEOUT_SECONDS
        try:
            return max(float(raw), 1.0)
        except ValueError:
            return DEFAULT_TIMEOUT_SECONDS

    # ------------ low-level subprocess runner --------------------------

    async def _run(self, argv: list[str], *, cmd: str) -> tuple[str, str]:
        """Run argv and return ``(stdout, stderr)`` text on success.

        Raises :class:`AGError` on non-zero exit or timeout. Both streams
        are captured as utf-8 with ``replace`` so binary garbage from a
        crashing build doesn't blow up the wrapper.
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
            raise AGError(timeout_message(cmd, timeout)) from exc

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        rc = proc.returncode if proc.returncode is not None else -1
        if rc != 0:
            raise map_returncode(rc, stderr, cmd=cmd)
        return stdout, stderr

    # ------------ helpers ----------------------------------------------

    @staticmethod
    def _arima_str(arima: tuple[int, int, int]) -> str:
        return f"{arima[0]},{arima[1]},{arima[2]}"

    @staticmethod
    def _garch_str(garch: tuple[int, int]) -> str:
        return f"{garch[0]},{garch[1]}"

    @staticmethod
    def _maybe_load_json(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as fp:
                return json.load(fp)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _read_csv_rows(path: Path, *, max_rows: int | None = None) -> list[dict[str, Any]]:
        """Read a small CSV without bringing in pandas for tiny outputs."""
        import csv

        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    coerced: dict[str, Any] = {}
                    for k, v in row.items():
                        if v is None:
                            coerced[k] = None
                            continue
                        s = v.strip()
                        if not s:
                            coerced[k] = None
                            continue
                        try:
                            coerced[k] = float(s)
                        except ValueError:
                            coerced[k] = s
                    rows.append(coerced)
                    if max_rows is not None and len(rows) >= max_rows:
                        break
        except (FileNotFoundError, OSError):
            return []
        return rows

    # ------------ subcommand methods -----------------------------------

    async def fit(
        self,
        *,
        data_path: Path,
        arima: tuple[int, int, int],
        garch: tuple[int, int],
        output_path: Path,
        innovation: Literal["gaussian", "student_t"] = "gaussian",
        t_df: float | None = None,
        no_header: bool = False,
    ) -> FitResult:
        """`ag fit -d <data> --arima p,d,q --garch p,q -o <model.json> [...]`.

        Returns a :class:`FitResult` whose ``parsed`` field merges the model
        JSON written by the CLI with whatever extra fields the stdout
        report contains (test p-values, Student-t recommendation, etc.).
        """
        binary = self._resolve_binary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        argv: list[str] = [
            str(binary),
            "fit",
            "-d",
            str(data_path),
            "--arima",
            self._arima_str(arima),
            "--garch",
            self._garch_str(garch),
            "-o",
            str(output_path),
        ]
        argv += _innovation_argv(innovation, t_df)
        if no_header:
            argv.append("--no-header")
        stdout, stderr = await self._run(argv, cmd="fit")
        parsed = parse_fit_stdout(stdout)
        if output_path.exists():
            model_json = self._maybe_load_json(output_path)
            if model_json:
                parsed = {**parsed, **parse_model_json(model_json)}
                parsed.setdefault("model_json", model_json)
        else:
            raise AGError(
                f"`ag fit` reported success but {output_path} was not written."
            )
        return FitResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            model_path=output_path,
            parsed=parsed,
        )

    async def select(
        self,
        *,
        data_path: Path,
        output_path: Path,
        max_p: int = 2,
        max_d: int = 1,
        max_q: int = 2,
        max_garch_p: int = 1,
        max_garch_q: int = 1,
        criterion: Literal["BIC", "AIC", "AICc", "CV"] = "BIC",
        top_k: int | None = None,
        no_header: bool = False,
    ) -> SelectResult:
        """`ag select -d <data> -o <model.json> --criterion BIC --max-p N ...`.

        Defaults are deliberately small (max-p/q = 2, max-d = 1, max-garch-
        p/q = 1) because the candidate grid is multiplicative. ``CV`` is
        slow — surface that to callers.
        """
        binary = self._resolve_binary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        argv: list[str] = [
            str(binary),
            "select",
            "-d",
            str(data_path),
            "-o",
            str(output_path),
            "--criterion",
            criterion,
            "--max-p",
            str(max_p),
            "--max-d",
            str(max_d),
            "--max-q",
            str(max_q),
            "--max-garch-p",
            str(max_garch_p),
            "--max-garch-q",
            str(max_garch_q),
        ]
        if top_k is not None:
            argv += ["--top-k", str(int(top_k))]
        if no_header:
            argv.append("--no-header")
        stdout, stderr = await self._run(argv, cmd="select")
        parsed = parse_fit_stdout(stdout)
        if output_path.exists():
            model_json = self._maybe_load_json(output_path)
            if model_json:
                parsed = {**parsed, **parse_model_json(model_json)}
                parsed.setdefault("model_json", model_json)
                parsed.setdefault("criterion", criterion)
        else:
            raise AGError(
                f"`ag select` reported success but {output_path} was not written."
            )
        return SelectResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            model_path=output_path,
            parsed=parsed,
        )

    async def forecast(
        self,
        *,
        model_path: Path,
        horizon: int,
        output_path: Path,
    ) -> ForecastResult:
        """`ag forecast -m <model.json> --horizon N -o <forecast.csv>`."""
        if horizon < 1:
            raise AGError(f"forecast horizon must be >= 1; got {horizon}")
        binary = self._resolve_binary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            str(binary),
            "forecast",
            "-m",
            str(model_path),
            "--horizon",
            str(int(horizon)),
            "-o",
            str(output_path),
        ]
        stdout, stderr = await self._run(argv, cmd="forecast")
        if not output_path.exists():
            raise AGError(
                f"`ag forecast` reported success but {output_path} was not written."
            )
        rows = self._read_csv_rows(output_path)
        return ForecastResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            forecast_csv=output_path,
            rows=rows,
        )

    async def simulate(
        self,
        *,
        model_path: Path,
        paths: int,
        length: int,
        output_path: Path,
        seed: int = 42,
        stats: bool = True,
    ) -> SimulateResult:
        """`ag simulate -m <model.json> --paths N --length N -o <sim.csv>`.

        With ``stats=True``, the CLI prints a summary of path-wise stats to
        stdout (mean, stdev, quantiles); we parse what we can and surface
        the file path either way.
        """
        if paths < 1 or length < 1:
            raise AGError("simulate paths and length must both be >= 1.")
        binary = self._resolve_binary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            str(binary),
            "simulate",
            "-m",
            str(model_path),
            "--paths",
            str(int(paths)),
            "--length",
            str(int(length)),
            "-o",
            str(output_path),
            "--seed",
            str(int(seed)),
        ]
        if stats:
            argv.append("--stats")
        stdout, stderr = await self._run(argv, cmd="simulate")
        if not output_path.exists():
            raise AGError(
                f"`ag simulate` reported success but {output_path} was not written."
            )
        parsed_stats = parse_simulate_stats_stdout(stdout)
        return SimulateResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            simulation_csv=output_path,
            parsed_stats=parsed_stats,
        )

    async def diagnostics(
        self,
        *,
        model_path: Path,
        data_path: Path,
        output_path: Path | None = None,
    ) -> DiagnosticsResult:
        """`ag diagnostics -m <model.json> -d <data.csv> [-o <diag.json>]`.

        Runs the Ljung-Box (raw and squared residuals), Jarque-Bera, and
        any other post-fit checks the CLI emits. The structured fields go
        into ``parsed``; the human-readable text stays in ``raw_stdout``.
        """
        binary = self._resolve_binary()
        argv = [
            str(binary),
            "diagnostics",
            "-m",
            str(model_path),
            "-d",
            str(data_path),
        ]
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            argv += ["-o", str(output_path)]
        stdout, stderr = await self._run(argv, cmd="diagnostics")
        parsed = parse_diagnostics_stdout(stdout)
        if output_path is not None and output_path.exists():
            diag_json = self._maybe_load_json(output_path)
            if diag_json:
                # Stdout-scraped fields take precedence only when missing
                # from the JSON file; structured JSON wins on conflict.
                merged = dict(parsed)
                merged.update(diag_json)
                parsed = merged
                parsed.setdefault("diagnostics_json", diag_json)
        return DiagnosticsResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            diagnostics_path=output_path if output_path and output_path.exists() else None,
            parsed=parsed,
        )

    async def sim(
        self,
        *,
        arima: tuple[int, int, int],
        garch: tuple[int, int],
        length: int,
        output_path: Path,
        seed: int = 42,
        innovation: Literal["gaussian", "student_t"] = "gaussian",
        t_df: float | None = None,
    ) -> SimResult:
        """`ag sim --arima p,d,q --garch p,q --length N -o <data.csv>`.

        Synthesizes a single returns series from a bare ARIMA-GARCH spec
        (no model JSON required). Useful for tests and didactic demos.
        """
        if length < 2:
            raise AGError("sim length must be >= 2.")
        binary = self._resolve_binary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            str(binary),
            "sim",
            "--arima",
            self._arima_str(arima),
            "--garch",
            self._garch_str(garch),
            "--length",
            str(int(length)),
            "-o",
            str(output_path),
            "--seed",
            str(int(seed)),
        ]
        argv += _innovation_argv(innovation, t_df)
        stdout, stderr = await self._run(argv, cmd="sim")
        if not output_path.exists():
            raise AGError(
                f"`ag sim` reported success but {output_path} was not written."
            )
        return SimResult(
            raw_stdout=stdout,
            raw_stderr=stderr,
            argv=argv,
            data_csv=output_path,
        )


# ---------- singleton -----------------------------------------------------

_singleton: AGRunner | None = None


def install_runner(runner: AGRunner | None) -> None:
    """Register the runner for tools to retrieve via :func:`get_runner`."""
    global _singleton
    _singleton = runner


def get_runner() -> AGRunner:
    if _singleton is None:
        raise AGError(
            "AGRunner is not initialized. The server's lifespan failed to start."
        )
    return _singleton
