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


async def test_execution_guide_resource_covers_key_paths():
    async with MCPClient(_server()) as c:
        contents = await c.read_resource("assemblix://guides/execution")
    text = contents[0].text
    # The three easy-to-get-wrong integration facts must be present.
    assert "/api/workflows/{workflowId}/execute" in text
    assert "/api/workflows/task/{executionId}" in text  # poll path (not /executions)
    assert "/api/executions/{executionId}/stream" in text  # SSE path
    assert "stream_delta" in text


async def test_integrate_workflow_prompt_registered():
    async with MCPClient(_server()) as c:
        prompts = await c.list_prompts()
    assert any(p.name == "integrate_workflow" for p in prompts)


async def test_jev_routing_example_is_valid_workflow():
    async with MCPClient(_server()) as c:
        contents = await c.read_resource("assemblix://examples/jev-routing")
    data = json.loads(contents[0].text)
    nodes = {n["id"]: n for n in data["nodes"]}
    assert {n["type"] for n in nodes.values()} == {"start", "jev", "condition", "agent", "end"}
    jev = next(n for n in nodes.values() if n["type"] == "jev")
    question_types = {q["type"] for q in jev["config"]["questions"]}
    assert {"noul", "choice"} <= question_types
    condition = next(n for n in nodes.values() if n["type"] == "condition")
    assert all("input.jev." in c["expression"] for c in condition["config"]["conditions"])
    for edge in data["edges"]:
        assert edge["source"] in nodes and edge["target"] in nodes
        if edge["source"] == condition["id"]:
            assert edge["sourceHandle"].startswith(f"source_{condition['id']}_")


async def test_author_prompt_mentions_jev():
    async with MCPClient(_server()) as c:
        prompt = await c.get_prompt("author_workflow")
    text = prompt.messages[0].content.text
    assert "jev" in text
    assert "list_credentials" in text
