"""Shared configuration / secrets loading.

A single repo-root ``.env`` is loaded once at process start. Connectors read
their own namespaced env vars (e.g. ``FMP_API_KEY``, ``FOO_API_KEY``); any
truly cross-connector value (e.g. a shared cache directory) is also pulled
from this same file by the consuming module.
"""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def load_env(dotenv_path: str | Path | None = None) -> None:
    """Load the repo-root .env into ``os.environ`` exactly once.

    Idempotent. Silently no-ops if ``python-dotenv`` is not installed or the
    file does not exist. Connectors call this from their server lifespan so
    every connector sees the same environment.
    """
    global _loaded
    if _loaded:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _loaded = True
        return
    if dotenv_path is None:
        load_dotenv()
    else:
        load_dotenv(dotenv_path=str(dotenv_path))
    _loaded = True


def require_env(name: str, *, hint: str | None = None) -> str:
    """Return ``os.environ[name]`` stripped, or raise with an actionable hint.

    The hint is appended to the error message; use it to tell the user where
    to put the key (e.g. ``"Set FMP_API_KEY in your .env file."``).
    """
    value = os.environ.get(name, "").strip()
    if not value:
        msg = f"{name} is not set."
        if hint:
            msg = f"{msg} {hint}"
        raise RuntimeError(msg)
    return value


def get_env(name: str, default: str | None = None) -> str | None:
    """Return ``os.environ[name]`` stripped, or ``default`` if unset/empty."""
    value = os.environ.get(name, "").strip()
    return value or default
