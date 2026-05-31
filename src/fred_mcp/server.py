"""FastMCP server entry point for the FRED connector.

Run with stdio transport. All logging goes to stderr so it doesn't corrupt
the MCP JSON-RPC stream on stdout.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from turningbull_mcp.config import load_env
from turningbull_mcp.logging import log_stderr

load_env()

from .client import FredClient, install_client, make_async_client
from .tools import categories, maps, releases, series, sources, tags


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    if not os.environ.get("FRED_API_KEY", "").strip():
        log_stderr(
            "fred-mcp: WARNING — FRED_API_KEY is not set. FRED rejects keyless "
            "requests, so tools will return an error until it is configured. "
            "Get a free key at https://fredaccount.stlouisfed.org/apikeys"
        )
    http = make_async_client()
    client = FredClient(http, api_key=os.environ.get("FRED_API_KEY", "").strip() or None)
    install_client(client)
    log_stderr("fred-mcp: started, client installed.")
    try:
        yield {"client": client}
    finally:
        await http.aclose()
        log_stderr("fred-mcp: shut down.")


mcp = FastMCP("fred_mcp", lifespan=lifespan)

for module in (categories, releases, series, sources, tags, maps):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``fred-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
