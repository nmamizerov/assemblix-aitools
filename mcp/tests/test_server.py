import asyncio
from unittest.mock import patch

import httpx
import respx
from fastmcp import Client as MCPClient
from starlette.datastructures import Headers

from assemblix_mcp.config import Settings
from assemblix_mcp.server import build_server


class _FakeRequest:
    """Stand-in for starlette Request; only .headers is read by get_http_headers."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = Headers(headers)
        self.scope: dict[str, object] = {}


@respx.mock
async def test_get_client_reads_authorization_header_over_http():
    """Regression test: hosted HTTP transport must forward the caller's bearer
    token to the API. fastmcp's get_http_headers() excludes "authorization" by
    default, so build_server's get_client() must pass include={"authorization"}
    to opt it back in. No ASSEMBLIX_API_KEY is set, so if the header is not
    read, resolve_api_key raises and this test fails.
    """
    settings = Settings(
        api_url="http://api.test", api_key=None, transport="http", host="h", port=1
    )
    mcp = build_server(settings)

    route = respx.get("http://api.test/api/workflows/").mock(
        return_value=httpx.Response(200, json=[])
    )

    fake_request = _FakeRequest(
        {"Authorization": "Bearer sk_from_header", "X-Benign": "yes"}
    )

    with patch("fastmcp.server.dependencies.get_http_request", return_value=fake_request):
        async with MCPClient(mcp) as c:
            result = await c.call_tool("list_workflows", {})

    assert result.data == []
    sent_auth = route.calls.last.request.headers["authorization"]
    assert sent_auth == "Bearer sk_from_header"


def test_build_server_registers_all_tools():
    settings = Settings(
        api_url="http://api.test", api_key="sk_k", transport="stdio", host="h", port=1
    )
    mcp = build_server(settings)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {
        "list_node_types",
        "create_workflow",
        "publish_workflow",
        "run_workflow",
        "run_workflow_and_wait",
        "get_execution",
        "list_executions",
    } <= names
