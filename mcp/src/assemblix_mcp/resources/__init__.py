"""Bundled example workflows + authoring prompt registered on the MCP server."""

from __future__ import annotations

from importlib import resources

from fastmcp import FastMCP

_EXAMPLES = resources.files("assemblix_mcp.resources") / "examples"


def _load(name: str) -> str:
    return (_EXAMPLES / name).read_text(encoding="utf-8")


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
