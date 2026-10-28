import httpx
import respx
from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.tools.credentials import register_credential_tools

CREDENTIALS = [
    {
        "id": "c1",
        "type": "typesafe_token",
        "name": "jev",
        "createdAt": "2026-10-28T00:00:00",
        "value": "must-not-leak",
    },
    {
        "id": "c2",
        "type": "openai_token",
        "name": None,
        "createdAt": "2026-10-28T00:00:00",
    },
]


def _server():
    mcp = FastMCP("test")

    async def get_client():
        return AssemblixClient(base_url="http://api.test", api_key="sk_k")

    register_credential_tools(mcp, get_client)
    return mcp


@respx.mock
async def test_list_credentials_strips_to_id_name_type():
    respx.get("http://api.test/api/credentials/").mock(
        return_value=httpx.Response(200, json=CREDENTIALS)
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_credentials", {})
    assert result.structured_content["result"] == [
        {"id": "c1", "name": "jev", "type": "typesafe_token"},
        {"id": "c2", "name": None, "type": "openai_token"},
    ]


@respx.mock
async def test_list_credentials_filters_by_type():
    route = respx.get("http://api.test/api/credentials/").mock(
        return_value=httpx.Response(200, json=CREDENTIALS)
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_credentials", {"type": "typesafe_token"})
    assert [item["id"] for item in result.structured_content["result"]] == ["c1"]
    assert route.calls.last.request.url.params["type"] == "typesafe_token"
