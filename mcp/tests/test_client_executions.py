import httpx
import respx

from assemblix_mcp.client import AssemblixClient


def _client():
    return AssemblixClient(base_url="http://api.test", api_key="sk_k")


@respx.mock
async def test_execute_workflow_task_mode_body():
    route = respx.post("http://api.test/api/workflows/w1/execute").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "running"})
    )
    result = await _client().execute_workflow("w1", input={"message": "hi"}, task=True)
    assert result["executionId"] == "e1"
    body = route.calls.last.request.content
    assert b'"input"' in body
    assert b'"task"' in body
    assert b"project_id" not in body and b"projectId" not in body


@respx.mock
async def test_get_task_result():
    respx.get("http://api.test/api/workflows/task/e1").mock(
        return_value=httpx.Response(200, json={"executionId": "e1", "status": "completed"})
    )
    result = await _client().get_task_result("e1")
    assert result["status"] == "completed"


@respx.mock
async def test_list_executions_snake_query():
    route = respx.get("http://api.test/api/executions/").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0, "page": 1, "limit": 50})
    )
    await _client().list_executions(workflow_id="w1")
    params = route.calls.last.request.url.params
    # project_id is never sent — the server derives it from the key.
    assert "project_id" not in params
    assert params["workflow_id"] == "w1"


@respx.mock
async def test_list_in_flight():
    respx.get("http://api.test/api/executions/in-flight").mock(
        return_value=httpx.Response(200, json=[{"id": "e1", "status": "RUNNING"}])
    )
    assert await _client().list_in_flight() == [{"id": "e1", "status": "RUNNING"}]
