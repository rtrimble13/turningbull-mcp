"""ARIMA-GARCH MCP server package.

Wraps the `ag` C++ CLI from the `arima-garch` project as MCP tools so an
LLM can fit, select, forecast, simulate, and diagnose univariate
ARIMA-GARCH models on top of data retrieved by sibling connectors
(`fmp_mcp`, `bls_mcp`, `bea_mcp`).
"""

__version__ = "0.1.0"
