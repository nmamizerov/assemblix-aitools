import httpx
import respx

from assemblix_mcp.client import AssemblixAPIError, AssemblixClient


def _client():
    return AssemblixClient(base_url="http://api.test", api_key="sk_k")


@respx.mock
async def test_list_workflows_sends_bearer_and_no_project():
    route = respx.get("http://api.test/api/workflows/").mock(
        return_value=httpx.Response(200, json=[{"id": "w1"}])
    )
    result = await _client().list_workflows(is_active=True)
    assert result == [{"id": "w1"}]
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk_k"
    # project_id is never sent — the server derives it from the key.
    assert "project_id" not in sent.url.params
    assert sent.url.params["is_active"] == "true"


@respx.mock
async def test_create_workflow_posts_camel_body_without_project():
    route = respx.post("http://api.test/api/workflows/").mock(
        return_value=httpx.Response(201, json={"id": "w2", "name": "New"})
    )
    result = await _client().create_workflow(name="New")
    assert result["id"] == "w2"
    body = route.calls.last.request.content
    assert b'"name"' in body
    # project is implicit in the key — never in the body.
    assert b"projectId" not in body and b"project_id" not in body


@respx.mock
async def test_error_response_raises_with_detail():
    respx.get("http://api.test/api/workflows/w9").mock(
        return_value=httpx.Response(403, json={"detail": "nope"})
    )
    try:
        await _client().get_workflow("w9")
        assert False, "expected error"
    except AssemblixAPIError as e:
        assert e.status_code == 403
        assert "nope" in e.detail
