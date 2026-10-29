"""Credential lookup. project_id is implicit in the API key; secrets are never returned."""

from __future__ import annotations

from typing import Awaitable, Callable

from fastmcp import FastMCP

from assemblix_mcp.client import AssemblixClient

GetClient = Callable[[], Awaitable[AssemblixClient]]


def register_credential_tools(mcp: FastMCP, get_client: GetClient) -> None:
    @mcp.tool
    async def list_credentials(type: str | None = None) -> list:
        """List the project's stored credentials as {id, name, type} — use an id as a
        node's credentialId (e.g. type='typesafe_token' for a jev node). Secrets are
        never returned; the user creates credentials in the Assemblix UI."""
        client = await get_client()
        items = await client.list_credentials(type=type)
        return [
            {"id": c["id"], "name": c.get("name"), "type": c["type"]}
            for c in items
            if type is None or c["type"] == type
        ]
