"""Bundled example workflows + authoring prompt registered on the MCP server."""

from __future__ import annotations

from importlib import resources

from fastmcp import FastMCP

_ROOT = resources.files("assemblix_mcp.resources")
_EXAMPLES = _ROOT / "examples"
_GUIDES = _ROOT / "guides"


def _load(name: str) -> str:
    return (_EXAMPLES / name).read_text(encoding="utf-8")


def _load_guide(name: str) -> str:
    return (_GUIDES / name).read_text(encoding="utf-8")


def register_resources(mcp: FastMCP) -> None:
    @mcp.resource("assemblix://examples/minimal")
    def minimal_example() -> str:
        """A runnable START -> AGENT -> END workflow (create -> update ->
        publish -> run). Shows the START node shape, which is not in
        list_node_types."""
        return _load("minimal.json")

    @mcp.resource("assemblix://examples/branching")
    def branching_example() -> str:
        """A START -> CONDITION -> two AGENT branches -> END workflow. Shows how
        condition branch edges use sourceHandle 'source_<conditionId>_<index>'."""
        return _load("branching.json")

    @mcp.resource("assemblix://guides/execution")
    def execution_guide() -> str:
        """How to integrate Assemblix workflow execution into a product: the
        /execute API, sync vs task+polling, SSE streaming, chat sessions, and
        voice/avatars — with curl/JS/Python examples. Read this before writing
        any code that calls a workflow (especially streaming)."""
        return _load_guide("execution.md")

    @mcp.resource("assemblix://guides/voice-agents")
    def voice_agents_guide() -> str:
        """How to build a voice agent and put it into a product: what a voice
        agent is (no graph — unlike voice inside a workflow), minting a call
        token, the WebSocket audio protocol and the three things people get
        wrong with it, attaching analysis workflows, and reading calls back.
        Read this before authoring a voice agent or writing any call client."""
        return _load_guide("voice-agents.md")

    @mcp.prompt
    def integrate_voice_agent() -> str:
        """Guidance for building an Assemblix voice agent and calling it."""
        return (
            "To build a voice agent and put it into a product:\n"
            "1. Read the resource assemblix://guides/voice-agents — it is the full "
            "how-to, including the WebSocket frame vocabulary.\n"
            "2. A voice agent has NO graph. It is a prompt plus a voice; workflows "
            "attach only as background analysis. Do not confuse it with voice "
            "inside a workflow (the transcribe node), which is a different feature.\n"
            "3. Author it with list_conversation_voices -> create_voice_agent. Never "
            "hand-write the nested `config` object; the tools assemble it. A "
            "provider/model/voice combination not in the catalog is rejected, and "
            "voice ids are case-sensitive.\n"
            "4. Write the prompt for speech: short sentences, no markdown, no lists "
            "the agent would have to read aloud.\n"
            "5. To call it: POST /api/voice-agents/{id}/sessions on YOUR backend "
            "with the sk_ key (never in the browser), then open "
            "wss://…/api/voice-agents/sessions/{token}/stream from the client. The "
            "token lives 60 seconds and authorizes one call.\n"
            "6. Three mistakes to avoid: sample rates come from the session.ready "
            "frame and differ per provider (never resample by hand); capture must "
            "start only after that frame; on speech.started you must stop() every "
            "queued audio source or the agent talks over the caller.\n"
            "7. Iterate on real calls: list_voice_calls -> get_voice_call, read the "
            "transcript, then update_voice_agent. Guessing from the prompt alone "
            "does not work."
        )

    @mcp.prompt
    def integrate_workflow() -> str:
        """Guidance for calling an Assemblix workflow from your own product."""
        return (
            "To integrate Assemblix workflow execution into a product (call a "
            "published workflow, stream tokens, keep a session, send voice):\n"
            "1. Read the resource assemblix://guides/execution — it is the full "
            "how-to with exact endpoints and curl/JS/Python examples.\n"
            "2. Key paths that are easy to get wrong:\n"
            "   - Run: POST /api/workflows/{workflowId}/execute\n"
            "   - Poll a task result: GET /api/workflows/task/{executionId} "
            "(under /api/workflows, NOT /api/executions)\n"
            "   - Subscribe to the token stream: GET /api/executions/{executionId}/stream "
            "(SSE; under /api/executions)\n"
            "3. Streaming = send `stream: true` on execute, then open the SSE stream "
            "with the returned executionId and read stream_delta events until "
            "execution_complete; resume with Last-Event-ID after drops.\n"
            "4. Talking-head avatar: mint a session with "
            "POST /api/workflows/{workflowId}/avatar/session, connect the returned "
            "provider SDK in audio-passthrough mode, and feed the avatar-flagged "
            "audio_delta chunks (data.avatar=true) into it — see guide §6 (avatars).\n"
            "5. Auth is the same project sk_ key (Bearer); projectId is never sent."
        )

    @mcp.prompt
    def author_workflow() -> str:
        """Guidance for authoring an Assemblix workflow via these tools."""
        return (
            "To author and run an Assemblix workflow:\n"
            "1. Call list_node_types to see AGENT/CONDITION/HTTP_REQUEST/"
            "SET_VARIABLE/DELAY/END config schemas. START is implicit and NOT "
            "listed — copy its shape from the example resources.\n"
            "2. Read assemblix://examples/minimal (and /branching) for the exact "
            "node/edge JSON shape: node = {id, type, position:{x,y}, config}, "
            "edge = {id, source, target, sourceHandle?}. CONDITION branch edges "
            "use sourceHandle 'source_<conditionNodeId>_<index>'.\n"
            "3. create_workflow -> update_workflow(nodes, edges, state) -> "
            "publish_workflow. Runs always execute the PUBLISHED snapshot, so "
            "publish after every change you want to run.\n"
            "4. run_workflow (async, poll get_execution) or run_workflow_and_wait. "
            'input usually is {"message": "..."}.\n'
            "5. Inspect with get_execution_detail / list_executions. AGENT nodes "
            "need a provider credential configured in the Assemblix UI; if missing, "
            "the run fails with a clear error."
        )
