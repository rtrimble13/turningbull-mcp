"""Logging helpers safe for MCP stdio transport.

MCP stdio servers reserve stdout for JSON-RPC; any log output must go to
stderr or the protocol stream gets corrupted.
"""

from __future__ import annotations

import sys


def log_stderr(msg: str) -> None:
    """Print to stderr with an immediate flush."""
    print(msg, file=sys.stderr, flush=True)
