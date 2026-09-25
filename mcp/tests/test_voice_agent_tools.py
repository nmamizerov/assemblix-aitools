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


_AGENT_WITH_EXTRAS = {
    "id": "va1",
    "config": {
        "instructions": [{"role": "system", "content": "Old prompt"}],
        "knowledgeBaseIds": [],
        "firstMessage": None,
        "language": "ru",
        "voice": {"provider": "openai", "model": "gpt-realtime-2.1", "voiceId": "marin"},
        "tts": {"provider": "elevenlabs", "model": "eleven_flash_v2_5", "voiceId": "v1"},
        "avatar": {
            "provider": "anam",
            "avatarModel": "cara-4",
            "avatarId": "av-old",
            "credentialId": "cred-anam",
        },
        "params": {},
        "turnWorkflowId": None,
        "finalWorkflowId": None,
    },
}


@respx.mock
async def test_editing_the_prompt_keeps_fields_the_tool_does_not_know():
    """The API replaces the whole config, so any key the tool does not rebuild
    (an external voice, an avatar, whatever comes next) must be carried over —
    otherwise a prompt edit silently strips the agent's face."""
    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json=_AGENT_WITH_EXTRAS)
    )
    route = respx.patch("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool("update_voice_agent", {"voice_agent_id": "va1", "system_prompt": "New"})

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["instructions"] == [{"role": "system", "content": "New"}]
    assert config["tts"] == _AGENT_WITH_EXTRAS["config"]["tts"]
    assert config["avatar"] == _AGENT_WITH_EXTRAS["config"]["avatar"]


@respx.mock
async def test_create_with_an_avatar_assembles_the_avatar_block():
    route = respx.post("http://api.test/api/voice-agents/").mock(
        return_value=httpx.Response(201, json={"id": "va2"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool(
            "create_voice_agent",
            {
                "name": "Face",
                "system_prompt": "Hi",
                "avatar_credential_id": "cred-anam",
                "avatar_id": "av-1",
                "avatar_model": "cara-4",
            },
        )

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["avatar"] == {
        "provider": "anam",
        "avatarModel": "cara-4",
        "avatarId": "av-1",
        "credentialId": "cred-anam",
    }


@respx.mock
async def test_create_without_an_avatar_sends_none():
    route = respx.post("http://api.test/api/voice-agents/").mock(
        return_value=httpx.Response(201, json={"id": "va3"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool("create_voice_agent", {"name": "Voice", "system_prompt": "Hi"})

    assert "avatar" not in json.loads(route.calls.last.request.content)["config"]


@respx.mock
async def test_update_changes_only_the_avatar_fields_passed():
    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json=_AGENT_WITH_EXTRAS)
    )
    route = respx.patch("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool("update_voice_agent", {"voice_agent_id": "va1", "avatar_id": "av-new"})

    assert json.loads(route.calls.last.request.content)["config"]["avatar"] == {
        "provider": "anam",
        "avatarModel": "cara-4",
        "avatarId": "av-new",
        "credentialId": "cred-anam",
    }


@respx.mock
async def test_remove_avatar_turns_the_agent_back_into_voice_only():
    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json=_AGENT_WITH_EXTRAS)
    )
    route = respx.patch("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool("update_voice_agent", {"voice_agent_id": "va1", "remove_avatar": True})

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["avatar"] is None
    assert config["tts"] == _AGENT_WITH_EXTRAS["config"]["tts"]


@respx.mock
async def test_list_avatars_returns_models_and_the_credential_avatars():
    respx.get("http://api.test/api/avatar/providers/anam/models").mock(
        return_value=httpx.Response(
            200, json=[{"id": "cara", "label": "Cara", "avatarModel": "cara-4"}]
        )
    )
    avatars = respx.get("http://api.test/api/avatar/credentials/cred-anam/avatars").mock(
        return_value=httpx.Response(200, json=[{"id": "av-1", "name": "Mia (desk)"}])
    )

    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_avatars", {"credential_id": "cred-anam"})

    assert avatars.called
    assert result.data == {
        "provider": "anam",
        "models": [{"id": "cara", "label": "Cara", "avatarModel": "cara-4"}],
        "avatars": [{"id": "av-1", "name": "Mia (desk)"}],
    }
