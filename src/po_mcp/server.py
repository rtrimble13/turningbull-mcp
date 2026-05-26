"""FastMCP server entry point for the portfolio-optimization connector.

Run with stdio transport. All logging goes to stderr so it doesn't
corrupt the MCP JSON-RPC stream on stdout.
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

from .runner import PORunner, install_runner
from .tools import composites, data, portfolios, primitives


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    """Resolve the `po` binary path and install the runner singleton.

    The binary is not opened here — we only check that something is
    resolvable. The first tool call will fail with a clear actionable
    message if the binary path turns out to be wrong, and the portopt-
    supplement tools lazy-import portopt independently.
    """
    bin_env = os.environ.get("PO_BINARY_PATH", "").strip()
    if not bin_env and not shutil.which("po"):
        log_stderr(
            "po-mcp: WARNING — neither PO_BINARY_PATH is set nor `po` is on "
            "PATH. CLI tools that call the binary will error until you "
            "build the `po` C++ project and point PO_BINARY_PATH at the "
            "compiled executable. portopt-supplement tools (HRP, ERC, "
            "backtest, attribution) only require the portopt Python "
            "module to be importable."
        )
    runner = PORunner(binary_path=bin_env or None)
    install_runner(runner)
    log_stderr("po-mcp: started, runner installed.")
    try:
        yield {"runner": runner}
    finally:
        install_runner(None)
        log_stderr("po-mcp: shut down.")


mcp = FastMCP("po_mcp", lifespan=lifespan)

for module in (primitives, portfolios, data, composites):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``po-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
