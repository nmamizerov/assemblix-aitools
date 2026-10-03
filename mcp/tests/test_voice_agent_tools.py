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


@respx.mock
async def test_create_cascade_defaults_to_a_fast_cheap_russian_pipeline():
    route = respx.post("http://api.test/api/voice-agents/").mock(
        return_value=httpx.Response(201, json={"id": "va4"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool(
            "create_voice_agent", {"name": "Cascade", "system_prompt": "Hi", "mode": "cascade"}
        )

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["mode"] == "cascade"
    assert config["voice"] is None
    assert config["tts"] == {
        "provider": "yandex",
        "model": "yandex-tts-v3-chunk",
        "voiceId": "alena",
        "credentialId": None,
        "realtime": True,
    }
    assert config["cascade"] == {
        "stt": {"provider": "yandex", "model": "general", "credentialId": None},
        "turn": {},
        "brain": {
            "type": "prompt",
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
            "credentialId": None,
            "params": {"thinking_level": "minimal", "max_tokens": 300},
        },
    }


@respx.mock
async def test_create_cascade_with_overrides():
    route = respx.post("http://api.test/api/voice-agents/").mock(
        return_value=httpx.Response(201, json={"id": "va5"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool(
            "create_voice_agent",
            {
                "name": "Cascade",
                "system_prompt": "Hi",
                "mode": "cascade",
                "brain_provider": "openai",
                "brain_model": "gpt-5.4-mini",
                "brain_credential_id": "cred-oai",
                "history_turns": 20,
                "stt_credential_id": "cred-ya",
                "tts_provider": "elevenlabs",
                "tts_model": "eleven_flash_v2_5",
                "tts_voice_id": "v1",
                "min_silence_ms": 300,
                "max_silence_ms": 2000,
                "smart_turn": False,
            },
        )

    config = json.loads(route.calls.last.request.content)["config"]
    assert config["tts"] == {
        "provider": "elevenlabs",
        "model": "eleven_flash_v2_5",
        "voiceId": "v1",
        "credentialId": None,
        "realtime": True,
    }
    cascade = config["cascade"]
    assert cascade["stt"]["credentialId"] == "cred-ya"
    assert cascade["turn"] == {"minSilenceMs": 300, "maxSilenceMs": 2000, "smartTurn": False}
    assert cascade["brain"] == {
        "type": "prompt",
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "credentialId": "cred-oai",
        "params": {"max_tokens": 300},
        "historyTurns": 20,
    }


async def test_cascade_arguments_are_refused_on_a_realtime_agent():
    async with MCPClient(_server()) as c:
        result = await c.call_tool(
            "create_voice_agent",
            {"name": "RT", "system_prompt": "Hi", "brain_model": "gemini-3.1-flash-lite"},
            raise_on_error=False,
        )

    assert result.is_error
    assert "mode='cascade'" in result.content[0].text


@respx.mock
async def test_switching_realtime_to_cascade_and_back_yields_valid_shapes():
    """The backend requires `voice` for realtime and `cascade` + `tts` for cascade,
    and rejects a `cascade` block on a realtime agent."""
    stored = json.loads(json.dumps(_AGENT_WITH_EXTRAS))
    del stored["config"]["tts"]
    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json=stored)
    )
    route = respx.patch("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool("update_voice_agent", {"voice_agent_id": "va1", "mode": "cascade"})

    to_cascade = json.loads(route.calls.last.request.content)["config"]
    assert to_cascade["mode"] == "cascade"
    assert to_cascade["voice"] is None
    assert to_cascade["tts"]["model"] == "yandex-tts-v3-chunk"
    assert to_cascade["cascade"]["brain"]["model"] == "gemini-3.1-flash-lite"
    assert to_cascade["avatar"] == stored["config"]["avatar"]

    respx.get("http://api.test/api/voice-agents/va1").mock(
        return_value=httpx.Response(200, json={"id": "va1", "config": to_cascade})
    )
    async with MCPClient(_server()) as c:
        await c.call_tool("update_voice_agent", {"voice_agent_id": "va1", "mode": "realtime"})

    back = json.loads(route.calls.last.request.content)["config"]
    assert back["mode"] == "realtime"
    assert back["cascade"] is None
    assert back["tts"] is None
    assert back["voice"] == {
        "provider": "openai",
        "model": "gpt-realtime-2.1",
        "voiceId": "marin",
        "credentialId": None,
    }
    assert back["instructions"] == stored["config"]["instructions"]


_CASCADE_AGENT = {
    "id": "va2",
    "config": {
        "mode": "cascade",
        "instructions": [{"role": "system", "content": "Speak briefly."}],
        "knowledgeBaseIds": [],
        "firstMessage": None,
        "language": "ru",
        "voice": None,
        "tts": {
            "provider": "yandex",
            "model": "yandex-tts-v3",
            "voiceId": "filipp",
            "credentialId": None,
            "realtime": True,
        },
        "cascade": {
            "stt": {"provider": "yandex", "model": "general", "credentialId": "cred-ya"},
            "turn": {
                "minSilenceMs": 200,
                "maxSilenceMs": 1500,
                "smartTurn": True,
                "smartTurnThreshold": 0.5,
                "prerollMs": 450,
            },
            "brain": {
                "type": "prompt",
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite",
                "credentialId": None,
                "params": {"thinking_level": "low"},
                "historyTurns": 80,
            },
            "futureKnob": 7,
        },
        "params": {},
        "turnWorkflowId": None,
        "finalWorkflowId": None,
    },
}


@respx.mock
async def test_cascade_update_overlays_only_what_was_passed():
    respx.get("http://api.test/api/voice-agents/va2").mock(
        return_value=httpx.Response(200, json=_CASCADE_AGENT)
    )
    route = respx.patch("http://api.test/api/voice-agents/va2").mock(
        return_value=httpx.Response(200, json={"id": "va2"})
    )

    async with MCPClient(_server()) as c:
        await c.call_tool(
            "update_voice_agent",
            {"voice_agent_id": "va2", "max_silence_ms": 1000, "tts_voice_id": "alena"},
        )

    config = json.loads(route.calls.last.request.content)["config"]
    stored = _CASCADE_AGENT["config"]
    assert config["mode"] == "cascade"
    assert config["voice"] is None
    assert config["tts"] == {**stored["tts"], "voiceId": "alena"}
    assert config["cascade"] == {
        **stored["cascade"],
        "turn": {**stored["cascade"]["turn"], "maxSilenceMs": 1000},
    }


@respx.mock
async def test_list_cascade_options_lists_brains_and_streaming_voices():
    for name in ("openai", "gemini", "deepseek"):
        respx.get(f"http://api.test/api/llm/providers/{name}/models").mock(
            return_value=httpx.Response(200, json=[{"id": f"{name}-m"}])
        )
    respx.get("http://api.test/api/voice/providers", params={"capability": "realtime"}).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "yandex", "label": "Yandex SpeechKit"},
                {"name": "elevenlabs", "label": "ElevenLabs"},
            ],
        )
    )
    for name in ("yandex", "elevenlabs"):
        respx.get(
            f"http://api.test/api/voice/providers/{name}/models", params={"capability": "realtime"}
        ).mock(return_value=httpx.Response(200, json=[{"id": f"{name}-stream"}]))
    respx.get("http://api.test/api/voice/providers/yandex/system-voices").mock(
        return_value=httpx.Response(200, json=[{"id": "alena", "name": "Alena (ru, f)"}])
    )
    respx.get("http://api.test/api/voice/providers/elevenlabs/system-voices").mock(
        return_value=httpx.Response(503, json={"detail": "System key not configured"})
    )

    async with MCPClient(_server()) as c:
        result = await c.call_tool("list_cascade_options", {})

    assert result.data["brain"]["gemini"] == [{"id": "gemini-m"}]
    assert result.data["tts"]["yandex"]["voices"] == [{"id": "alena", "name": "Alena (ru, f)"}]
    assert result.data["tts"]["elevenlabs"]["models"] == [{"id": "elevenlabs-stream"}]
    assert "System key not configured" in result.data["tts"]["elevenlabs"]["voices"]
