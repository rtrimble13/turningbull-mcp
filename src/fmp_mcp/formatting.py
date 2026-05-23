"""Back-compat re-export.

The actual implementation lives in :mod:`turningbull_mcp.formatting` so other
connectors can share it. This module is kept so existing imports like
``from fmp_mcp.formatting import render`` keep working.
"""

from turningbull_mcp.formatting import render  # noqa: F401
