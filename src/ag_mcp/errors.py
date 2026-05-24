"""AG-specific error helpers.

Inherits from :class:`ConnectorError` so the generic ``wrap_error`` helper
formats AG failures the same way it formats FMP/BLS/BEA failures.
"""

from __future__ import annotations

from turningbull_mcp.errors import ConnectorError, empty_result_message  # noqa: F401


class AGError(ConnectorError):
    """Surface-level error from the `ag` CLI returned as a tool result."""


def binary_not_found_message() -> str:
    """Message shown when neither $AG_BINARY_PATH nor `which ag` resolves."""
    return (
        "ag binary not found. Build the arima-garch C++ project first "
        "(see arima-garch/README.md), then set AG_BINARY_PATH in your .env "
        "to the absolute path of the compiled `ag` executable (typically "
        "`<repo>/build/ninja-release/src/ag`). Alternatively, place `ag` "
        "on your PATH."
    )


def map_returncode(rc: int, stderr: str, *, cmd: str) -> AGError:
    """Render a CLI failure as an AGError with the binary's own stderr."""
    snippet = stderr.strip()
    if len(snippet) > 1200:
        snippet = snippet[:1200] + " …(truncated)"
    if not snippet:
        snippet = "(no stderr)"
    return AGError(
        f"`ag {cmd}` failed with exit code {rc}. stderr: {snippet}"
    )


def timeout_message(cmd: str, timeout: float) -> str:
    return (
        f"`ag {cmd}` timed out after {timeout:.0f}s. For `ag select` with "
        "criterion=CV, reduce max-p/max-q or switch to criterion=BIC; for "
        "long simulations, reduce paths or length."
    )
