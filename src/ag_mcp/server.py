"""FastMCP server entry point for the ARIMA-GARCH connector.

Run with stdio transport. All logging goes to stderr so it doesn't corrupt
the MCP JSON-RPC stream on stdout.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from turningbull_mcp.config import load_env
from turningbull_mcp.logging import log_stderr

load_env()

from .runner import AGRunner, install_runner
from .tools import composites, data, primitives


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    """Resolve the `ag` binary path and install the runner singleton.

    The binary is not opened here — we only check that something is
    resolvable. The first tool call will fail with a clear actionable
    message if the binary path turns out to be wrong.
    """
    bin_env = os.environ.get("AG_BINARY_PATH", "").strip()
    if not bin_env and not shutil.which("ag"):
        log_stderr(
            "ag-mcp: WARNING — neither AG_BINARY_PATH is set nor `ag` is on "
            "PATH. Tools that call the binary will error until you build "
            "the arima-garch C++ project and point AG_BINARY_PATH at the "
            "compiled `ag` executable."
        )
    runner = AGRunner(binary_path=bin_env or None)
    install_runner(runner)
    log_stderr("ag-mcp: started, runner installed.")
    try:
        yield {"runner": runner}
    finally:
        install_runner(None)
        log_stderr("ag-mcp: shut down.")


mcp = FastMCP("ag_mcp", lifespan=lifespan)

for module in (primitives, data, composites):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``ag-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
