"""Connector-agnostic Pydantic models and enums.

Anything domain-specific (tickers, intervals, indicator names) lives in the
connector's own ``models`` module. Things here apply to any MCP connector:
date validation, response shape selection, large-output mode selection.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import BeforeValidator, Field

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not DATE_RE.match(s):
        raise ValueError(f"date must be YYYY-MM-DD, got {value!r}")
    return s


OptionalDate = Annotated[
    str | None,
    BeforeValidator(_validate_date),
    Field(default=None, description="ISO date YYYY-MM-DD."),
]

RequiredDate = Annotated[
    str,
    BeforeValidator(_validate_date),
    Field(description="ISO date YYYY-MM-DD."),
]


class ResponseFormat(str, Enum):
    markdown = "markdown"
    json = "json"


class OutputMode(str, Enum):
    summary = "summary"
    inline = "inline"
