import httpx
import respx
from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.tools.executions import register_execution_tools


def _server():
    mcp = FastMCP("test")

    async def get_client():
        return AssemblixClient(base_url="http://api.test", api_key="sk_k", project_id="p1")

    register_execution_tools(mcp, get_client)
    return mcp


@respx.mock
async def test_run_workflow_returns_execution_id():
    respx.post("http://api.test/api/workflows/w1/execute").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool("run_workflow", {"workflow_id": "w1", "input": {"message": "hi"}})
    assert result.data["executionId"] == "e1"


@respx.mock
async def test_run_and_wait_polls_until_completed():
    respx.post("http://api.test/api/workflows/w1/execute").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    respx.get("http://api.test/api/executions/task/e1").mock(
        side_effect=[
            httpx.Response(200, json={"executionId": "e1", "status": "running"}),
            httpx.Response(200, json={"executionId": "e1", "status": "completed", "output": {"a": 1}}),
        ]
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool(
            "run_workflow_and_wait",
            {"workflow_id": "w1", "input": {"message": "hi"}, "poll_interval": 0, "timeout_seconds": 5},
        )
    assert result.data["status"] == "completed"
    assert result.data["output"] == {"a": 1}


@respx.mock
async def test_run_and_wait_returns_error_payload_without_raising():
    respx.post("http://api.test/api/workflows/w1/execute").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    respx.get("http://api.test/api/executions/task/e1").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "failed", "error": "no credential"})
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool(
            "run_workflow_and_wait",
            {"workflow_id": "w1", "input": {"message": "hi"}, "poll_interval": 0, "timeout_seconds": 5},
        )
    assert result.data["status"] == "failed"
    assert result.data["error"] == "no credential"


@respx.mock
async def test_run_and_wait_times_out_when_never_terminal():
    respx.post("http://api.test/api/workflows/w1/execute").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    respx.get("http://api.test/api/executions/task/e1").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    async with MCPClient(_server()) as c:
        result = await c.call_tool(
            "run_workflow_and_wait",
            {"workflow_id": "w1", "input": {"message": "hi"}, "poll_interval": 0, "timeout_seconds": 0.05},
        )
    assert result.data["timedOut"] is True
    assert result.data["status"] == "running"
