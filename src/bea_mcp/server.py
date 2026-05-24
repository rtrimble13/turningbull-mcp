"""FastMCP server entry point for the BEA connector.

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

from .client import BEAClient, install_client, make_async_client
from .tools import (
    composites,
    discovery,
    generic,
    industry,
    international,
    national,
    regional,
)


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict]:
    if not os.environ.get("BEA_API_KEY", "").strip():
        log_stderr(
            "bea-mcp: WARNING — BEA_API_KEY is not set. The BEA API requires "
            "a 36-character UserID for every call. Register for a free key "
            "at https://apps.bea.gov/API/signup/ and add it to your .env."
        )
    http = make_async_client()
    client = BEAClient(http)
    install_client(client)
    log_stderr("bea-mcp: started, client installed.")
    try:
        yield {"client": client}
    finally:
        await http.aclose()
        install_client(None)
        log_stderr("bea-mcp: shut down.")


mcp = FastMCP("bea_mcp", lifespan=lifespan)

for module in (
    discovery,
    generic,
    national,
    international,
    industry,
    regional,
    composites,
):
    module.register(mcp)


def main() -> None:
    """Entry point used by the ``bea-mcp`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
