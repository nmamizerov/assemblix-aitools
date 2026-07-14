"""Run & inspect tools. project_id is implicit in the API key."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastmcp import FastMCP

from assemblix_mcp.tools.workflows import GetClient

_PENDING = {"running", "queued", "pending"}


def _is_terminal(payload: Any) -> bool:
    status = str((payload or {}).get("status", "")).lower()
    return status not in _PENDING


def register_execution_tools(mcp: FastMCP, get_client: GetClient) -> None:
    @mcp.tool
    async def run_workflow(
        workflow_id: str,
        input: dict,
        state: dict | None = None,
        project_state: dict | None = None,
        client_id: str | None = None,
        metadata: dict | None = None,
    ) -> Any:
        """Start the published workflow asynchronously. Returns immediately with
        an executionId; poll it with get_execution. `input` typically holds a
        'message' field. Publish the workflow first."""
        client = await get_client()
        return await client.execute_workflow(
            workflow_id,
            input=input,
            task=True,
            state=state,
            project_state=project_state,
            client_id=client_id,
            metadata=metadata,
        )

    @mcp.tool
    async def run_workflow_and_wait(
        workflow_id: str,
        input: dict,
        state: dict | None = None,
        project_state: dict | None = None,
        timeout_seconds: float = 120.0,
        poll_interval: float = 2.0,
    ) -> Any:
        """Start the published workflow and poll until it finishes or the timeout
        elapses. Returns the final result — including an error payload on failure
        (does not raise). On timeout returns the last status with timedOut=true."""
        client = await get_client()
        started = await client.execute_workflow(
            workflow_id,
            input=input,
            task=True,
            state=state,
            project_state=project_state,
        )
        if _is_terminal(started):
            return started
        execution_id = str(started["executionId"])
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            result = await client.get_task_result(execution_id)
            if _is_terminal(result):
                return result
        return {"executionId": execution_id, "status": "running", "timedOut": True}

    @mcp.tool
    async def get_execution(execution_id: str) -> Any:
        """Get the status/result of one run (poll after run_workflow). Returns
        status 'running' while in progress, else the completed or error payload."""
        client = await get_client()
        return await client.get_task_result(execution_id)

    @mcp.tool
    async def list_executions(
        workflow_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> Any:
        """List the project's run history (paginated). status is one of QUEUED,
        RUNNING, COMPLETED, ERROR, FAILED. Dates are ISO 8601."""
        client = await get_client()
        return await client.list_executions(
            workflow_id=workflow_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            page=page,
            limit=limit,
        )

    @mcp.tool
    async def get_execution_detail(execution_id: str) -> Any:
        """Get step-level detail for a run (node inputs/outputs, errors, timing) —
        use this to diagnose why a run failed."""
        client = await get_client()
        return await client.get_execution_detail(execution_id)

    @mcp.tool
    async def list_in_flight() -> list:
        """List runs currently QUEUED or RUNNING in the project."""
        client = await get_client()
        return await client.list_in_flight()
