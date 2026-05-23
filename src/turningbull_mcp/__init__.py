"""Shared utilities for the turningbull-mcp connector suite.

This package holds connector-agnostic building blocks (HTTP retry, dataset
output, response formatting, common Pydantic types, config loading) that any
MCP connector in this repo can reuse. Connectors live in sibling packages
(e.g. ``fmp_mcp``) and own their own API client, error mapping, and tool
modules.
"""

__version__ = "0.1.0"
