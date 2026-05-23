"""Shared error base classes and helpers.

Each connector defines its own concrete exception (e.g. ``FMPError``) that
subclasses :class:`ConnectorError`. Tool dispatch code can catch the base
class to format any connector failure uniformly.
"""

from __future__ import annotations


class ConnectorError(Exception):
    """Surface-level error returned to the caller as a tool result.

    Connectors raise subclasses of this to get consistent formatting from
    :func:`turningbull_mcp.tool_helpers.wrap_error`.
    """


def empty_result_message(what: str) -> str:
    """Render the canonical 'no rows returned' message for ``what``."""
    return (
        f"No data returned for {what}. The symbol, range, or filter may have "
        "no matches."
    )
