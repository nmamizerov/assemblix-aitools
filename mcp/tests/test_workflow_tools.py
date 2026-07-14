import httpx
import respx
from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.tools.workflows import register_workflow_tools


def _server():
    mcp = FastMCP("test")

    async def get_client():
        return AssemblixClient(base_url="http://api.test", api_key="sk_k", project_id="p1")

    register_workflow_tools(mcp, get_client)
    return mcp


@respx.mock
async def test_list_node_types_tool():
    respx.get("http://api.test/api/nodes").mock(
        return_value=httpx.Response(200, json=[{"type": "agent"}])
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_node_types", {})
    assert result.data == [{"type": "agent"}]


@respx.mock
async def test_create_then_publish():
    respx.post("http://api.test/api/workflows/").mock(
        return_value=httpx.Response(201, json={"id": "w2", "name": "New"})
    )
    respx.post("http://api.test/api/workflows/w2/publish").mock(
        return_value=httpx.Response(200, json={"id": "w2", "isPublished": True})
    )
    async with MCPClient(_server()) as c:
        created = await c.call_tool("create_workflow", {"name": "New"})
        published = await c.call_tool("publish_workflow", {"workflow_id": "w2"})
    assert created.data["id"] == "w2"
    assert published.data["isPublished"] is True
