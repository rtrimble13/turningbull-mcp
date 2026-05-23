"""FastMCP server entry point for the BLS connector.

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

from .client import BLSClient, install_client, make_async_client
from .tools import series


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    if not os.environ.get("BLS_API_KEY", "").strip():
        log_stderr(
            "bls-mcp: WARNING — BLS_API_KEY is not set. Falling back to v1 "
            "(25 queries/day, 10-year cap, no calculations/annual-average/"
            "catalog). Register at https://data.bls.gov/registrationEngine/ "
            "for a free key."
        )
    http = make_async_client()
    client = BLSClient(http)
    install_client(client)
    log_stderr("bls-mcp: started, client installed.")
    try:
        yield {"client": client}
    finally:
        await http.aclose()
        log_stderr("bls-mcp: shut down.")


mcp = FastMCP("bls_mcp", lifespan=lifespan)

for module in (series,):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``bls-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
