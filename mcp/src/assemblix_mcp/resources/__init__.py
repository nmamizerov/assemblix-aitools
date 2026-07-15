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
            "4. Auth is the same project sk_ key (Bearer); projectId is never sent."
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
            "input usually is {\"message\": \"...\"}.\n"
            "5. Inspect with get_execution_detail / list_executions. AGENT nodes "
            "need a provider credential configured in the Assemblix UI; if missing, "
            "the run fails with a clear error."
        )
