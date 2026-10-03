"""Voice agent tools. project_id is implicit in the API key.

A voice agent has no graph: it is a prompt, a voice, knowledge bases inlined into
the prompt at call time, and up to two workflows that observe the conversation.
The voice is either one speech-to-speech model (``realtime`` mode) or a chain of
streaming STT, a text LLM and streaming TTS (``cascade`` mode). Its whole
configuration lives in one nested ``config`` object, which these tools assemble
from flat arguments — the nesting is an artifact of how the API stores it, and
asking a model to reproduce it by hand invites a wrong shape on every call.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixAPIError
from assemblix_mcp.tools.workflows import GetClient

Mode = Literal["realtime", "cascade"]

# What a fresh realtime voice is when an agent leaves cascade without one.
_REALTIME_VOICE = {"provider": "openai", "model": "gpt-realtime-2.1", "voiceId": "marin"}

# Cheapest streaming synthesis with a Russian voice.
_CASCADE_TTS = {
    "provider": "yandex",
    "model": "yandex-tts-v3-chunk",
    "voiceId": "alena",
    "credentialId": None,
    "realtime": True,
}
_CASCADE_STT = {"provider": "yandex", "model": "general", "credentialId": None}
_BRAIN_PROVIDERS = ("openai", "gemini", "deepseek")
_BRAIN_PROVIDER = "gemini"
_BRAIN_MODEL = "gemini-3.1-flash-lite"


def _keep(new: Any, current: Any) -> Any:
    """An omitted argument means "leave this alone", not "clear it"."""
    return current if new is None else new


def _default_brain_params(provider: str, model: str) -> dict:
    """Short replies, and no thinking before the first token where the model allows it."""
    params: dict = {"max_tokens": 300}
    if provider == "gemini" and model.startswith("gemini-3"):
        params = {"thinking_level": "minimal", **params}
    return params


def _merge_tts(
    current: dict | None,
    *,
    provider: str | None,
    model: str | None,
    voice_id: str | None,
    credential_id: str | None,
) -> dict | None:
    """Overlay the tts_* arguments that were passed onto the current speech output.

    A different provider starts from nothing: model, voice and credential do not
    carry across providers.
    """
    if provider is None and model is None and voice_id is None and credential_id is None:
        return current
    base = current or {}
    if provider is not None and provider != base.get("provider"):
        base = {}
    tts = {
        **base,
        "provider": _keep(provider, base.get("provider")),
        "model": _keep(model, base.get("model")),
        "voiceId": _keep(voice_id, base.get("voiceId")),
        "credentialId": _keep(credential_id, base.get("credentialId")),
        "realtime": True,
    }
    if not tts["provider"] or not tts["model"] or not tts["voiceId"]:
        raise ValueError(
            "A new speech output needs tts_provider, tts_model and tts_voice_id "
            "together (see list_cascade_options)"
        )
    return tts


def _require_cascade_for(mode: str, cascade_args: dict) -> None:
    passed = [name for name, value in cascade_args.items() if value is not None]
    if mode != "cascade" and passed:
        raise ValueError(f"{', '.join(passed)} only apply with mode='cascade'")


def _merge_cascade(
    current: dict | None,
    *,
    stt_credential_id: str | None,
    brain_provider: str | None,
    brain_model: str | None,
    brain_credential_id: str | None,
    brain_params: dict | None,
    history_turns: int | None,
    min_silence_ms: int | None,
    max_silence_ms: int | None,
    smart_turn: bool | None,
    smart_turn_threshold: float | None,
) -> dict:
    """Overlay the cascade arguments that were passed onto the agent's cascade block,
    keeping every key this tool has no argument for."""
    base = current or {}
    stt = {**_CASCADE_STT, **(base.get("stt") or {})}
    stt["credentialId"] = _keep(stt_credential_id, stt.get("credentialId"))

    turn = dict(base.get("turn") or {})
    for key, value in (
        ("minSilenceMs", min_silence_ms),
        ("maxSilenceMs", max_silence_ms),
        ("smartTurn", smart_turn),
        ("smartTurnThreshold", smart_turn_threshold),
    ):
        if value is not None:
            turn[key] = value

    old = base.get("brain") or {}
    if brain_provider is not None and brain_provider != old.get("provider"):
        # Model ids, credentials and tunables are all provider-specific.
        old = {}
    provider = _keep(brain_provider, old.get("provider", _BRAIN_PROVIDER))
    if provider not in _BRAIN_PROVIDERS:
        raise ValueError(f"brain_provider must be one of {', '.join(_BRAIN_PROVIDERS)}")
    model = _keep(brain_model, old.get("model"))
    if model is None:
        if provider != _BRAIN_PROVIDER:
            raise ValueError(
                f"brain_model is required for brain_provider {provider!r} "
                "(see list_cascade_options)"
            )
        model = _BRAIN_MODEL
    if brain_params is not None:
        params = brain_params
    elif "params" in old:
        params = old["params"]
    else:
        params = _default_brain_params(provider, model)
    brain = {
        **old,
        "type": "prompt",
        "provider": provider,
        "model": model,
        "credentialId": _keep(brain_credential_id, old.get("credentialId")),
        "params": params,
    }
    if history_turns is not None:
        brain["historyTurns"] = history_turns
    return {**base, "stt": stt, "turn": turn, "brain": brain}


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


def _merge_avatar(
    current: dict | None,
    *,
    provider: str | None,
    credential_id: str | None,
    avatar_id: str | None,
    avatar_model: str | None,
) -> dict | None:
    """Overlay the avatar arguments that were passed onto the agent's current avatar.

    Nothing passed means the current avatar (or its absence) stands.
    """
    if provider is None and credential_id is None and avatar_id is None and avatar_model is None:
        return current
    base = current or {"provider": "anam", "avatarModel": "", "avatarId": None, "credentialId": None}
    return {
        "provider": _keep(provider, base.get("provider", "anam")),
        "avatarModel": _keep(avatar_model, base.get("avatarModel", "")),
        "avatarId": _keep(avatar_id, base.get("avatarId")),
        "credentialId": _keep(credential_id, base.get("credentialId")),
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
    async def list_cascade_options() -> dict:
        """List what a cascade voice agent (mode="cascade") is assembled from: the
        text-brain LLMs per provider (brain_provider/brain_model), and the
        streaming speech-output providers with their models and voices
        (tts_provider/tts_model/tts_voice_id). Speech recognition is Yandex
        SpeechKit and needs no choice.

        Only the models listed under `tts` can speak a cascade — a buffered
        (non-streaming) TTS model is rejected when the call starts. Voices are
        those of the platform key; an ElevenLabs voice cloned on the user's own
        key is not listed here but works by id with tts_credential_id."""
        client = await get_client()
        brain = {name: await client.list_llm_models(name) for name in _BRAIN_PROVIDERS}
        tts = {}
        for provider in await client.list_voice_providers("realtime"):
            name = provider["name"]
            try:
                voices: Any = await client.list_provider_system_voices(name)
            except AssemblixAPIError as exc:
                voices = f"not listable here: {exc.detail}"
            tts[name] = {
                "label": provider["label"],
                "models": await client.list_voice_provider_models(name, "realtime"),
                "voices": voices,
            }
        return {"brain": brain, "tts": tts}

    @mcp.tool
    async def list_avatars(credential_id: str, provider: str = "anam") -> dict:
        """List what a voice agent's avatar can be set to: the provider's avatar
        models and the avatars (faces) available to one avatar credential.

        credential_id is an avatar-provider credential (an Anam API key) the user
        added in the Assemblix UI under Credentials — it is BYO-only, there is no
        platform key. Call this before create_voice_agent/update_voice_agent with
        avatar_* arguments: avatar_id must be one of the returned avatars and
        avatar_model one of the returned models' `avatarModel`."""
        client = await get_client()
        return {
            "provider": provider,
            "models": await client.list_avatar_models(provider),
            "avatars": await client.list_credential_avatars(credential_id),
        }

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
        mode: Mode = "realtime",
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
        brain_provider: str | None = None,
        brain_model: str | None = None,
        brain_credential_id: str | None = None,
        brain_params: dict | None = None,
        history_turns: int | None = None,
        stt_credential_id: str | None = None,
        tts_provider: str | None = None,
        tts_model: str | None = None,
        tts_voice_id: str | None = None,
        tts_credential_id: str | None = None,
        min_silence_ms: int | None = None,
        max_silence_ms: int | None = None,
        smart_turn: bool | None = None,
        smart_turn_threshold: float | None = None,
        avatar_credential_id: str | None = None,
        avatar_id: str | None = None,
        avatar_model: str | None = None,
        avatar_provider: str = "anam",
    ) -> Any:
        """Create a voice agent.

        mode="realtime" (default) runs the call on one speech-to-speech model:
        provider/model/voice_id must come from list_conversation_voices.

        mode="cascade" runs it as streaming speech recognition (Yandex) → a text
        LLM (the brain) → streaming speech synthesis. Cheaper per hour, better
        Russian, no provider session cap; provider/model/voice_id are ignored.
        Pick brain_* and tts_* from list_cascade_options. Omitted, they default
        to brain gemini/gemini-3.1-flash-lite with brain_params
        {"thinking_level": "minimal", "max_tokens": 300} and voice
        yandex/yandex-tts-v3-chunk/alena. Keep thinking minimal and replies
        short: every token before the first word is silence on the line.
        min_silence_ms, max_silence_ms, smart_turn and smart_turn_threshold tune
        when the caller counts as finished. The server needs turn-detection
        models and SpeechKit keys; read the "Cascade mode" section of
        assemblix://guides/voice-agents before choosing it.

        stt_credential_id (a Yandex SpeechKit credential), brain_credential_id and
        tts_credential_id are optional: omitted, the platform keys are used.

        The prompt is spoken aloud, so write it for speech: short sentences, no
        markdown, no lists the agent would have to read out.

        first_message is what the agent says before the caller speaks; leave it
        empty and the agent waits.

        turn_workflow_id runs in the background after every caller utterance and
        final_workflow_id once when the call ends — both observe only, neither can
        change what the agent says. Author them with the workflow tools first;
        read assemblix://guides/voice-agents for what they receive as input.

        If those workflows are meant to accumulate anything about the caller
        (a score, a profile, a running total), the call must be minted with a
        clientId — that is what binds the call and its hook runs to one client
        session, and so to one copy of project state. The guide covers it.

        To give the agent a lip-synced face, pass avatar_credential_id, avatar_id
        and avatar_model (all three, from list_avatars). The call's media then runs
        through the Assemblix server's LiveKit, which must be configured, or the
        API rejects the agent. Read the "Avatar calls" section of
        assemblix://guides/voice-agents before writing the client.
        """
        cascade_args = {
            "stt_credential_id": stt_credential_id,
            "brain_provider": brain_provider,
            "brain_model": brain_model,
            "brain_credential_id": brain_credential_id,
            "brain_params": brain_params,
            "history_turns": history_turns,
            "min_silence_ms": min_silence_ms,
            "max_silence_ms": max_silence_ms,
            "smart_turn": smart_turn,
            "smart_turn_threshold": smart_turn_threshold,
        }
        _require_cascade_for(mode, cascade_args)
        client = await get_client()
        config = _build_config(
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
        )
        tts = _merge_tts(
            dict(_CASCADE_TTS) if mode == "cascade" else None,
            provider=tts_provider,
            model=tts_model,
            voice_id=tts_voice_id,
            credential_id=tts_credential_id,
        )
        if mode == "cascade":
            config["mode"] = "cascade"
            config["voice"] = None
            config["cascade"] = _merge_cascade(None, **cascade_args)
        if tts is not None:
            config["tts"] = tts
        avatar = _merge_avatar(
            None,
            provider=avatar_provider if avatar_id or avatar_credential_id or avatar_model else None,
            credential_id=avatar_credential_id,
            avatar_id=avatar_id,
            avatar_model=avatar_model,
        )
        if avatar is not None:
            config["avatar"] = avatar
        return await client.create_voice_agent(name=name, description=description, config=config)

    @mcp.tool
    async def update_voice_agent(
        voice_agent_id: str,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        mode: Mode | None = None,
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
        brain_provider: str | None = None,
        brain_model: str | None = None,
        brain_credential_id: str | None = None,
        brain_params: dict | None = None,
        history_turns: int | None = None,
        stt_credential_id: str | None = None,
        tts_provider: str | None = None,
        tts_model: str | None = None,
        tts_voice_id: str | None = None,
        tts_credential_id: str | None = None,
        min_silence_ms: int | None = None,
        max_silence_ms: int | None = None,
        smart_turn: bool | None = None,
        smart_turn_threshold: float | None = None,
        avatar_credential_id: str | None = None,
        avatar_id: str | None = None,
        avatar_model: str | None = None,
        avatar_provider: str | None = None,
        remove_avatar: bool = False,
    ) -> Any:
        """Change a voice agent. Only the fields you pass are touched — the rest
        are read from the current agent and written back unchanged, so a prompt
        edit cannot silently reset the voice.

        Note the API replaces the whole config object, so this tool reads before
        it writes; two concurrent edits will not merge. Config fields this tool has
        no argument for (future ones, cascade tunables like prerollMs) are carried
        over.

        mode switches the engine. To "cascade": the realtime voice is dropped,
        the agent's tts is kept if it has one (else yandex/yandex-tts-v3-chunk/
        alena), and the brain defaults as in create_voice_agent. To "realtime":
        the cascade block and its speech output are dropped and the stored
        realtime voice comes back (openai/gpt-realtime-2.1/marin if there was
        none) — pass tts_* to keep an external voice.

        brain_*, stt_credential_id, history_turns and the turn arguments
        (min_silence_ms, max_silence_ms, smart_turn, smart_turn_threshold) apply
        to cascade agents only. A different brain_provider resets the brain's
        model, credential and params: pass brain_model with it. tts_* change only
        the fields passed; a different tts_provider needs tts_model and
        tts_voice_id too (see list_cascade_options).

        avatar_* arguments change only the avatar fields passed (see list_avatars);
        remove_avatar=True turns the agent back into a voice-only agent.
        """
        cascade_args = {
            "stt_credential_id": stt_credential_id,
            "brain_provider": brain_provider,
            "brain_model": brain_model,
            "brain_credential_id": brain_credential_id,
            "brain_params": brain_params,
            "history_turns": history_turns,
            "min_silence_ms": min_silence_ms,
            "max_silence_ms": max_silence_ms,
            "smart_turn": smart_turn,
            "smart_turn_threshold": smart_turn_threshold,
        }
        tts_args = {
            "provider": tts_provider,
            "model": tts_model,
            "voice_id": tts_voice_id,
            "credential_id": tts_credential_id,
        }
        client = await get_client()
        current = await client.get_voice_agent(voice_agent_id)
        config = current["config"]
        was = config.get("mode") or "realtime"
        target = mode or was
        _require_cascade_for(target, cascade_args)
        leaving_cascade = was == "cascade" and target == "realtime"
        voice = config.get("voice") or (_REALTIME_VOICE if leaving_cascade else {})
        instructions = config.get("instructions") or [{"role": "system", "content": ""}]

        # Start from the stored config so keys this tool does not rebuild survive.
        merged = {**config, **_build_config(
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
        )}
        if target == "cascade":
            merged["mode"] = "cascade"
            merged["voice"] = None
            merged["tts"] = _merge_tts(config.get("tts") or dict(_CASCADE_TTS), **tts_args)
            merged["cascade"] = _merge_cascade(config.get("cascade"), **cascade_args)
        else:
            if leaving_cascade:
                merged["mode"] = "realtime"
                merged["cascade"] = None
            if leaving_cascade or any(value is not None for value in tts_args.values()):
                merged["tts"] = _merge_tts(
                    None if leaving_cascade else config.get("tts"), **tts_args
                )
        merged["avatar"] = (
            None
            if remove_avatar
            else _merge_avatar(
                config.get("avatar"),
                provider=avatar_provider,
                credential_id=avatar_credential_id,
                avatar_id=avatar_id,
                avatar_model=avatar_model,
            )
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
        it ended, how many lines were spoken, and the clientId the call was minted
        with (null if anonymous). Use get_voice_call for the transcript."""
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
