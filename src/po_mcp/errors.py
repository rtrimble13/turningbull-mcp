"""PO-specific error helpers.

Inherits from :class:`ConnectorError` so the generic ``wrap_error`` helper
formats PO failures the same way it formats FMP/BLS/BEA/AG failures.
"""

from __future__ import annotations

from turningbull_mcp.errors import ConnectorError, empty_result_message  # noqa: F401


class POError(ConnectorError):
    """Surface-level error from the `po` CLI (or the lazy `portopt` import)
    returned as a tool result."""


def binary_not_found_message() -> str:
    """Message shown when neither $PO_BINARY_PATH nor `which po` resolves."""
    return (
        "po binary not found. Build the portfolio-optimization C++ project "
        "first (see https://github.com/rtrimble13/po), then set "
        "PO_BINARY_PATH in your .env to the absolute path of the compiled "
        "`po` executable (typically `<repo>/build/cli/po`). Alternatively, "
        "place `po` on your PATH."
    )


def portopt_not_importable_message() -> str:
    """Message shown when a portopt-supplement tool can't import portopt."""
    return (
        "portopt Python module could not be imported. The tool you called "
        "requires the portopt pybind11 extension (HRP, risk parity, "
        "walk-forward backtest, Brinson attribution, or arbitrary-weights "
        "summary). Build the portopt extension from the `po` repository "
        "and either install it into the active virtualenv "
        "(`pip install <repo>/build/python`) or extend PYTHONPATH to "
        "include `<repo>/build/python`. CLI-only tools (po_mvo, po_frontier, "
        "po_min_variance, …) work without portopt."
    )


def map_returncode(rc: int, stderr: str, *, cmd: str) -> POError:
    """Render a CLI failure as a POError with the binary's own stderr."""
    snippet = stderr.strip()
    if len(snippet) > 1200:
        snippet = snippet[:1200] + " …(truncated)"
    if not snippet:
        snippet = "(no stderr)"
    return POError(
        f"`po {cmd}` failed with exit code {rc}. stderr: {snippet}"
    )


def timeout_message(cmd: str, timeout: float) -> str:
    return (
        f"`po {cmd}` timed out after {timeout:.0f}s. For long frontiers, "
        "reduce frontier_points; for walk-forward backtests, increase the "
        "step size or shrink the rebalance window."
    )
