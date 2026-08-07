"""Voice agent tools. project_id is implicit in the API key.

A voice agent has no graph: it is a prompt, a speech-to-speech voice, knowledge
bases inlined into the prompt at call time, and up to two workflows that observe
the conversation. Its whole configuration lives in one nested ``config`` object,
which these tools assemble from flat arguments — the nesting is an artifact of how
the API stores it, and asking a model to reproduce it by hand invites a wrong
shape on every call.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from assemblix_mcp.tools.workflows import GetClient


def _keep(new: Any, current: Any) -> Any:
    """An omitted argument means "leave this alone", not "clear it"."""
    return current if new is None else new


def _build_config(
    *,
    system_prompt: str,
    provider: str,
    model: str,
    voice_id: str,
    language: str,
    first_message: str | None,
    knowledge_base_ids: list[str] | None,
    turn_workflow_id: str | None,
    final_workflow_id: str | None,
    credential_id: str | None,
    params: dict | None,
) -> dict:
    return {
        "instructions": [{"role": "system", "content": system_prompt}],
        "knowledgeBaseIds": knowledge_base_ids or [],
        "firstMessage": first_message,
        "language": language,
        "voice": {
            "provider": provider,
            "model": model,
            "voiceId": voice_id,
            "credentialId": credential_id,
        },
        "params": params or {},
        "turnWorkflowId": turn_workflow_id,
        "finalWorkflowId": final_workflow_id,
    }


def register_voice_agent_tools(mcp: FastMCP, get_client: GetClient) -> None:
    @mcp.tool
    async def list_conversation_voices() -> dict:
        """List everything a voice agent can be configured to speak with: the
        speech-to-speech providers, their models with per-minute cost, and each
        provider's voice ids. Call this before create_voice_agent — a provider,
        model or voice id that is not in here is rejected at creation, and voice
        ids are case-sensitive."""
        client = await get_client()
        providers = await client.list_voice_providers()
        catalog = {}
        for provider in providers:
            name = provider["name"]
            catalog[name] = {
                "label": provider["label"],
                "models": await client.list_voice_provider_models(name),
                "voices": await client.list_provider_system_voices(name),
            }
        return catalog

    @mcp.tool
    async def list_voice_agents() -> list:
        """List the project's voice agents."""
        client = await get_client()
        return await client.list_voice_agents()

    @mcp.tool
    async def get_voice_agent(voice_agent_id: str) -> Any:
        """Get one voice agent: its prompt, voice, knowledge bases, analysis
        workflows, and how many calls it has taken."""
        client = await get_client()
        return await client.get_voice_agent(voice_agent_id)

    @mcp.tool
    async def create_voice_agent(
        name: str,
        system_prompt: str,
        provider: str = "openai",
        model: str = "gpt-realtime-2.1",
        voice_id: str = "marin",
        language: str = "ru",
        description: str | None = None,
        first_message: str | None = None,
        knowledge_base_ids: list[str] | None = None,
        turn_workflow_id: str | None = None,
        final_workflow_id: str | None = None,
        credential_id: str | None = None,
        params: dict | None = None,
    ) -> Any:
        """Create a voice agent.

        provider/model/voice_id must come from list_conversation_voices. The
        prompt is spoken aloud, so write it for speech: short sentences, no
        markdown, no lists the agent would have to read out.

        first_message is what the agent says before the caller speaks; leave it
        empty and the agent waits.

        turn_workflow_id runs in the background after every caller utterance and
        final_workflow_id once when the call ends — both observe only, neither can
        change what the agent says. Author them with the workflow tools first;
        read assemblix://guides/voice-agents for what they receive as input.
        """
        client = await get_client()
        return await client.create_voice_agent(
            name=name,
            description=description,
            config=_build_config(
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                voice_id=voice_id,
                language=language,
                first_message=first_message,
                knowledge_base_ids=knowledge_base_ids,
                turn_workflow_id=turn_workflow_id,
                final_workflow_id=final_workflow_id,
                credential_id=credential_id,
                params=params,
            ),
        )

    @mcp.tool
    async def update_voice_agent(
        voice_agent_id: str,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        voice_id: str | None = None,
        language: str | None = None,
        first_message: str | None = None,
        knowledge_base_ids: list[str] | None = None,
        turn_workflow_id: str | None = None,
        final_workflow_id: str | None = None,
        credential_id: str | None = None,
        params: dict | None = None,
        is_active: bool | None = None,
    ) -> Any:
        """Change a voice agent. Only the fields you pass are touched — the rest
        are read from the current agent and written back unchanged, so a prompt
        edit cannot silently reset the voice.

        Note the API replaces the whole config object, so this tool reads before
        it writes; two concurrent edits will not merge.
        """
        client = await get_client()
        current = await client.get_voice_agent(voice_agent_id)
        config = current["config"]
        voice = config.get("voice", {})
        instructions = config.get("instructions") or [{"role": "system", "content": ""}]

        merged = _build_config(
            system_prompt=_keep(system_prompt, instructions[0].get("content", "")),
            provider=_keep(provider, voice.get("provider", "openai")),
            model=_keep(model, voice.get("model", "")),
            voice_id=_keep(voice_id, voice.get("voiceId", "")),
            language=_keep(language, config.get("language", "ru")),
            first_message=_keep(first_message, config.get("firstMessage")),
            knowledge_base_ids=_keep(knowledge_base_ids, config.get("knowledgeBaseIds", [])),
            turn_workflow_id=_keep(turn_workflow_id, config.get("turnWorkflowId")),
            final_workflow_id=_keep(final_workflow_id, config.get("finalWorkflowId")),
            credential_id=_keep(credential_id, voice.get("credentialId")),
            params=_keep(params, config.get("params", {})),
        )
        return await client.update_voice_agent(
            voice_agent_id,
            name=name,
            description=description,
            config=merged,
            is_active=is_active,
        )

    @mcp.tool
    async def delete_voice_agent(voice_agent_id: str) -> Any:
        """Delete a voice agent and its recorded calls."""
        client = await get_client()
        return await client.delete_voice_agent(voice_agent_id)

    @mcp.tool
    async def list_voice_calls(
        voice_agent_id: str, page: int = 1, limit: int = 50
    ) -> Any:
        """List an agent's calls, newest first: when, how long, what it cost, how
        it ended, and how many lines were spoken. Use get_voice_call for the
        transcript."""
        client = await get_client()
        return await client.list_voice_sessions(voice_agent_id, page=page, limit=limit)

    @mcp.tool
    async def get_voice_call(voice_session_id: str) -> Any:
        """Get one call: the full transcript, token counts, and every analysis
        workflow run it started (each with an executionId you can open with
        get_execution_detail).

        This is how you find out whether a prompt actually works. Read real
        transcripts before editing the prompt — what an agent does wrong on a call
        is rarely what you would guess from reading its instructions.
        """
        client = await get_client()
        return await client.get_voice_session(voice_session_id)
