import asyncio

from assemblix_mcp.config import Settings
from assemblix_mcp.server import build_server


def test_build_server_registers_all_tools():
    settings = Settings(
        api_url="http://api.test", api_key="sk_k", transport="stdio", host="h", port=1
    )
    mcp = build_server(settings)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {
        "list_node_types",
        "create_workflow",
        "publish_workflow",
        "run_workflow",
        "run_workflow_and_wait",
        "get_execution",
        "list_executions",
    } <= names
