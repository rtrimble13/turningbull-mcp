"""Shared HTTP primitives: httpx client factory and retry backoff."""

from __future__ import annotations

import random

import httpx


def make_async_client(
    *,
    user_agent: str = "turningbull-mcp/0.1",
    connect_timeout: float = 10.0,
    read_timeout: float = 60.0,
    write_timeout: float = 30.0,
    pool_timeout: float = 10.0,
    max_connections: int = 20,
    max_keepalive: int = 10,
) -> httpx.AsyncClient:
    """Build a default httpx async client suitable for a connector.

    The caller owns the client's lifetime — wire it to the server's lifespan
    so it closes cleanly on shutdown.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        ),
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
        ),
        headers={"User-Agent": user_agent},
    )


RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def backoff_seconds(attempt: int, *, cap: float = 30.0, jitter: float = 0.5) -> float:
    """Exponential backoff with jitter, capped at ``cap`` seconds."""
    base = min(2 ** attempt, cap)
    return base + random.uniform(0, jitter)
