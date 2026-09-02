import json

import httpx
import respx
from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.tools.projects import register_project_tools

COUNTER = {"name": "counter", "type": "number", "defaultValue": 0}
LANG = {"name": "lang", "type": "string", "defaultValue": "ru"}


def _server():
    mcp = FastMCP("test")

    async def get_client():
        return AssemblixClient(base_url="http://api.test", api_key="sk_k")

    register_project_tools(mcp, get_client)
    return mcp


@respx.mock
async def test_list_state_variables_sends_no_project():
    route = respx.get("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[COUNTER])
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_project_state_variables", {})
    assert result.data == [COUNTER]
    assert "project_id" not in route.calls.last.request.url.params


@respx.mock
async def test_set_state_variables_replaces_whole_list():
    route = respx.put("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[COUNTER, LANG])
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool(
            "set_project_state_variables", {"variables": [COUNTER, LANG]}
        )
    assert result.data == [COUNTER, LANG]
    assert json.loads(route.calls.last.request.content) == {
        "stateSchema": [COUNTER, LANG]
    }


@respx.mock
async def test_upsert_replaces_one_and_keeps_the_rest():
    respx.get("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[COUNTER, LANG])
    )
    route = respx.put("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with MCPClient(_server()) as c:
        await c.call_tool(
            "upsert_project_state_variable",
            {"name": "lang", "type": "string", "default_value": "en"},
        )
    sent = json.loads(route.calls.last.request.content)["stateSchema"]
    assert sent == [COUNTER, {"name": "lang", "type": "string", "defaultValue": "en"}]


@respx.mock
async def test_delete_keeps_the_other_variables():
    respx.get("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[COUNTER, LANG])
    )
    route = respx.put("http://api.test/api/projects/state").mock(
        return_value=httpx.Response(200, json=[COUNTER])
    )
    async with MCPClient(_server()) as c:
        await c.call_tool("delete_project_state_variable", {"name": "lang"})
    assert json.loads(route.calls.last.request.content) == {"stateSchema": [COUNTER]}
