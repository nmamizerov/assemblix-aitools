import json

import httpx
import respx
from fastmcp import Client as MCPClient
from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.tools.voice_agents import register_voice_agent_tools


def _server():
    mcp = FastMCP("test")

    async def get_client():
        return AssemblixClient(base_url="http://api.test", api_key="sk_k")

    register_voice_agent_tools(mcp, get_client)
    return mcp


@respx.mock
async def test_editing_the_prompt_keeps_the_rest_of_the_config():
    """The API replaces the whole config object, so a partial edit that forgot to
    read the current one would silently reset the agent's voice, language and
    analysis hooks. The tool must merge, not overwrite."""
    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "va1",
                "config": {
                    "instructions": [{"role": "system", "content": "Old prompt"}],
                    "knowledgeBaseIds": ["kb1"],
                    "firstMessage": "Hello!",
                    "language": "ru",
                    "voice": {
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-live-preview",
                        "voiceId": "Puck",
                        "credentialId": "cred1",
                    },
                    "params": {"silence_duration_ms": 500},
                    "turnWorkflowId": "wf-turn",
                    "finalWorkflowId": "wf-final",
                },
            },
        )
    )
    route = respx.patch("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool(
            "update_voice_agent",
            {"voice_agent_id": "va1", "system_prompt": "New prompt"},
        )

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["instructions"] == [{"role": "system", "content": "New prompt"}]
    assert config["voice"] == {
        "provider": "gemini",
        "model": "gemini-3.1-flash-live-preview",
        "voiceId": "Puck",
        "credentialId": "cred1",
    }
    assert config["language"] == "ru"
    assert config["firstMessage"] == "Hello!"
    assert config["knowledgeBaseIds"] == ["kb1"]
    assert config["params"] == {"silence_duration_ms": 500}
    assert config["turnWorkflowId"] == "wf-turn"
    assert config["finalWorkflowId"] == "wf-final"
