from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import TypeAdapter, ValidationError

from fmp_mcp.client import FMPClient, install_client
from fmp_mcp.models import CIK, OptionalCIK, ResponseFormat
from fmp_mcp.tools import multiasset
from tests.test_smoke import _assert_not_error


async def _call(server: FastMCP, name: str, **kwargs: object) -> str:
    result = await server.call_tool(name, kwargs)
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(
        getattr(chunk, "text", "")
        for chunk in content
        if getattr(chunk, "type", None) == "text"
    )


def test_cik_rejects_blank_input() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CIK).validate_python("   ")


def test_optional_cik_treats_blank_as_none() -> None:
    assert TypeAdapter(OptionalCIK).validate_python("   ") is None


@pytest.mark.parametrize(
    ("tool_name", "path", "dataset_name"),
    [
        ("fmp_get_all_forex_quotes", "/stable/batch-forex-quotes", "forex_quotes"),
        ("fmp_get_all_crypto_quotes", "/stable/batch-crypto-quotes", "crypto_quotes"),
        ("fmp_get_all_commodity_quotes", "/stable/batch-commodity-quotes", "commodity_quotes"),
    ],
)
async def test_batch_quote_tools_default_to_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool_name: str,
    path: str,
    dataset_name: str,
) -> None:
    rows = [{"symbol": "AAA", "price": 1.23}, {"symbol": "BBB", "price": 4.56}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == path
        return httpx.Response(200, json=rows)

    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setenv("FMP_OUTPUT_DIR", str(tmp_path))
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    install_client(FMPClient(http))

    mcp = FastMCP("fmp_mcp_test")
    multiasset.register(mcp)
    try:
        text = await _call(
            mcp, tool_name, response_format=ResponseFormat.json.value
        )
        payload = json.loads(text)
        assert payload["row_count"] == len(rows)
        assert sorted(Path(p).suffix for p in payload["files"]) == [".csv", ".parquet"]
        assert all(Path(p).exists() for p in payload["files"])
        assert all(dataset_name in Path(p).name for p in payload["files"])
    finally:
        install_client(None)  # type: ignore[arg-type]
        await http.aclose()


def test_assert_not_error_rejects_fmp_error_markup() -> None:
    with pytest.raises(AssertionError):
        _assert_not_error("**FMPError.** boom")
