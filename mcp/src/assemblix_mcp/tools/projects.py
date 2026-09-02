"""Project state schema tools. project_id is implicit in the API key."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient

GetClient = Callable[[], Awaitable[AssemblixClient]]


def register_project_tools(mcp: FastMCP, get_client: GetClient) -> None:
    @mcp.tool
    async def list_project_state_variables() -> list:
        """List the project's state variables — the state shared across a client's
        workflow runs. Each is {name, type: number|string|boolean|object,
        defaultValue}. Workflow-local state lives on the workflow instead."""
        client = await get_client()
        return await client.get_project_state_schema()

    @mcp.tool
    async def set_project_state_variables(variables: list) -> list:
        """Replace ALL project state variables with the given list — anything
        omitted is deleted. Call list_project_state_variables first and send the
        full list back, or use upsert_project_state_variable to change one."""
        client = await get_client()
        return await client.set_project_state_schema(variables)

    @mcp.tool
    async def upsert_project_state_variable(
        name: str,
        type: str,
        default_value: Any = None,
    ) -> list:
        """Add a project state variable, or replace the one with this name,
        leaving the others untouched. type is number|string|boolean|object."""
        client = await get_client()
        current = await client.get_project_state_schema() or []
        variable = {"name": name, "type": type, "defaultValue": default_value}
        updated = [v for v in current if v.get("name") != name] + [variable]
        return await client.set_project_state_schema(updated)

    @mcp.tool
    async def delete_project_state_variable(name: str) -> list:
        """Delete the project state variable with this name, leaving the others
        untouched."""
        client = await get_client()
        current = await client.get_project_state_schema() or []
        remaining = [v for v in current if v.get("name") != name]
        return await client.set_project_state_schema(remaining)
