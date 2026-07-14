"""Workflow authoring tools. project_id is implicit in the API key."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient

GetClient = Callable[[], Awaitable[AssemblixClient]]


def register_workflow_tools(mcp: FastMCP, get_client: GetClient) -> None:
    @mcp.tool
    async def list_node_types() -> list:
        """List available node types with their config schemas, for building a
        workflow graph. Note: START is implicit and not listed here — see the
        example workflows (resources) for its shape and the create->update->
        publish->run lifecycle."""
        client = await get_client()
        return await client.list_node_types()

    @mcp.tool
    async def list_workflows(
        is_active: bool | None = None,
        is_published: bool | None = None,
        is_template: bool | None = None,
    ) -> list:
        """List the project's workflows (optionally filtered by status)."""
        client = await get_client()
        return await client.list_workflows(
            is_active=is_active, is_published=is_published, is_template=is_template
        )

    @mcp.tool
    async def get_workflow(workflow_id: str) -> Any:
        """Get a workflow by id, including its nodes, edges and state."""
        client = await get_client()
        return await client.get_workflow(workflow_id)

    @mcp.tool
    async def create_workflow(name: str, description: str | None = None) -> Any:
        """Create a new draft workflow in the project. Add nodes/edges with
        update_workflow, then publish_workflow before running."""
        client = await get_client()
        return await client.create_workflow(name=name, description=description)

    @mcp.tool
    async def update_workflow(
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        nodes: list | None = None,
        edges: list | None = None,
        state: list | None = None,
    ) -> Any:
        """Replace a draft workflow's fields. nodes/edges/state fully replace the
        existing graph when provided; omit to leave unchanged."""
        client = await get_client()
        return await client.update_workflow(
            workflow_id,
            name=name,
            description=description,
            nodes=nodes,
            edges=edges,
            state=state,
        )

    @mcp.tool
    async def publish_workflow(workflow_id: str) -> Any:
        """Publish the draft as the runnable snapshot. run_workflow always
        executes the published version, so publish after every edit you want to
        run."""
        client = await get_client()
        return await client.publish_workflow(workflow_id)
