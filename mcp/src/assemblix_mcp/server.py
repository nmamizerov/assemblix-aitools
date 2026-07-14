"""FastMCP server assembly and entry point."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from assemblix_mcp.client import AssemblixClient
from assemblix_mcp.config import Settings, resolve_api_key
from assemblix_mcp.resources import register_resources
from assemblix_mcp.tools.executions import register_execution_tools
from assemblix_mcp.tools.workflows import register_workflow_tools


def build_server(settings: Settings) -> FastMCP:
    mcp = FastMCP("assemblix")

    async def get_client() -> AssemblixClient:
        headers = get_http_headers(include={"authorization"}) or {}
        api_key = resolve_api_key(settings, headers.get("authorization"))
        return AssemblixClient(base_url=settings.api_url, api_key=api_key)

    register_workflow_tools(mcp, get_client)
    register_execution_tools(mcp, get_client)
    register_resources(mcp)
    return mcp


def main() -> None:
    settings = Settings.from_env()
    mcp = build_server(settings)
    if settings.transport == "http":
        mcp.run(transport="http", host=settings.host, port=settings.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
