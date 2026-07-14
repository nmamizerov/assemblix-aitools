import json

from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.resources import register_resources


def _server():
    mcp = FastMCP("test")
    register_resources(mcp)
    return mcp


async def test_minimal_example_is_valid_runnable_shape():
    async with MCPClient(_server()) as c:
        contents = await c.read_resource("assemblix://examples/minimal")
    data = json.loads(contents[0].text)
    types = [n["type"] for n in data["nodes"]]
    assert types == ["start", "agent", "end"]
    # edges wire start->agent->end
    pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("start-1", "agent-1") in pairs
    assert ("agent-1", "end-1") in pairs


async def test_branching_example_uses_condition_handles():
    async with MCPClient(_server()) as c:
        contents = await c.read_resource("assemblix://examples/branching")
    data = json.loads(contents[0].text)
    handles = {e.get("sourceHandle") for e in data["edges"]}
    assert "source_cond-1_0" in handles
    assert "source_cond-1_1" in handles


async def test_author_prompt_registered():
    async with MCPClient(_server()) as c:
        prompts = await c.list_prompts()
    assert any(p.name == "author_workflow" for p in prompts)
