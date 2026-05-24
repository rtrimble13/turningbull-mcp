"""FastMCP server entry point for the FMP connector.

Run with stdio transport. All logging goes to stderr so it doesn't corrupt the
MCP JSON-RPC stream on stdout.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from turningbull_mcp.config import load_env
from turningbull_mcp.logging import log_stderr

load_env()

from .client import FMPClient, install_client, make_async_client
from .tools import (
    calendars,
    classification,
    composites,
    corporate,
    estimates,
    etf,
    filings,
    financials,
    indexes,
    macro,
    movers,
    multiasset,
    news,
    ownership,
    prices,
    screener,
    technicals,
    transcripts,
    valuation,
)


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    if not os.environ.get("FMP_API_KEY", "").strip():
        log_stderr(
            "fmp-mcp: WARNING — FMP_API_KEY is not set. Tools will return an "
            "error until it is configured."
        )
    http = make_async_client()
    client = FMPClient(http)
    install_client(client)
    log_stderr("fmp-mcp: started, client installed.")
    try:
        yield {"client": client}
    finally:
        await http.aclose()
        log_stderr("fmp-mcp: shut down.")


mcp = FastMCP("fmp_mcp", lifespan=lifespan)

for module in (
    prices,
    news,
    financials,
    corporate,
    classification,
    indexes,
    macro,
    screener,
    technicals,
    calendars,
    estimates,
    transcripts,
    valuation,
    ownership,
    filings,
    movers,
    etf,
    multiasset,
    composites,
):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``fmp-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
