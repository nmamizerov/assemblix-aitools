"""Thin async HTTP client over the Assemblix REST API.

Wire contract: query params are snake_case; request bodies are camelCase;
responses are camelCase. ``project_id`` is never sent — the server derives it
from the project-scoped API key.
"""

from __future__ import annotations

from typing import Any

import httpx


class AssemblixAPIError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


class AssemblixClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        async with httpx.AsyncClient(base_url=self._base, headers=self._headers) as http:
            resp = await http.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            raise AssemblixAPIError(resp.status_code, _extract_detail(resp))
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- nodes ---
    async def list_node_types(self) -> Any:
        return await self._request("GET", "/api/nodes")

    # --- project state schema ---
    async def get_project_state_schema(self) -> Any:
        return await self._request("GET", "/api/projects/state")

    async def set_project_state_schema(self, state_schema: list) -> Any:
        return await self._request(
            "PUT", "/api/projects/state", json={"stateSchema": state_schema}
        )

    # --- workflows ---
    async def list_workflows(
        self,
        is_active: bool | None = None,
        is_published: bool | None = None,
        is_template: bool | None = None,
    ) -> Any:
        params = _clean(
            {
                "is_active": is_active,
                "is_published": is_published,
                "is_template": is_template,
            }
        )
        return await self._request("GET", "/api/workflows/", params=params)

    async def get_workflow(self, workflow_id: str) -> Any:
        return await self._request("GET", f"/api/workflows/{workflow_id}")

    async def create_workflow(
        self,
        name: str | None = None,
        description: str | None = None,
        nodes: list | None = None,
        edges: list | None = None,
        state: list | None = None,
    ) -> Any:
        body = _clean(
            {
                "name": name,
                "description": description,
                "nodes": nodes,
                "edges": edges,
                "state": state,
            }
        )
        return await self._request("POST", "/api/workflows/", json=body)

    async def update_workflow(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        nodes: list | None = None,
        edges: list | None = None,
        state: list | None = None,
    ) -> Any:
        body = _clean(
            {
                "name": name,
                "description": description,
                "nodes": nodes,
                "edges": edges,
                "state": state,
            }
        )
        return await self._request("PATCH", f"/api/workflows/{workflow_id}", json=body)

    async def publish_workflow(self, workflow_id: str) -> Any:
        return await self._request("POST", f"/api/workflows/{workflow_id}/publish")

    # --- execution ---
    async def execute_workflow(
        self,
        workflow_id: str,
        input: dict,
        task: bool = False,
        state: dict | None = None,
        project_state: dict | None = None,
        client_id: str | None = None,
        metadata: dict | None = None,
    ) -> Any:
        body = _clean(
            {
                "input": input,
                "task": task,
                "state": state,
                "projectState": project_state,
                "clientId": client_id,
                "metadata": metadata,
            }
        )
        return await self._request(
            "POST", f"/api/workflows/{workflow_id}/execute", json=body
        )

    async def get_task_result(self, execution_id: str) -> Any:
        # Note: the task-result endpoint lives on the /workflows-prefixed router,
        # not /executions (unlike list/detail/in-flight below).
        return await self._request("GET", f"/api/workflows/task/{execution_id}")

    async def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> Any:
        params = _clean(
            {
                "workflow_id": workflow_id,
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
                "page": page,
                "limit": limit,
            }
        )
        return await self._request("GET", "/api/executions/", params=params)

    async def get_execution_detail(self, execution_id: str) -> Any:
        return await self._request("GET", f"/api/executions/{execution_id}")

    async def list_in_flight(self) -> Any:
        return await self._request("GET", "/api/executions/in-flight")

    # --- voice agents ---
    async def list_voice_agents(self) -> Any:
        return await self._request("GET", "/api/voice-agents/")

    async def get_voice_agent(self, voice_agent_id: str) -> Any:
        return await self._request("GET", f"/api/voice-agents/{voice_agent_id}")

    async def create_voice_agent(
        self, name: str, config: dict, description: str | None = None
    ) -> Any:
        body = _clean({"name": name, "description": description, "config": config})
        return await self._request("POST", "/api/voice-agents/", json=body)

    async def update_voice_agent(
        self,
        voice_agent_id: str,
        name: str | None = None,
        description: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
    ) -> Any:
        body = _clean(
            {
                "name": name,
                "description": description,
                "config": config,
                "isActive": is_active,
            }
        )
        return await self._request(
            "PATCH", f"/api/voice-agents/{voice_agent_id}", json=body
        )

    async def delete_voice_agent(self, voice_agent_id: str) -> Any:
        return await self._request("DELETE", f"/api/voice-agents/{voice_agent_id}")

    # --- voice calls ---
    async def list_voice_sessions(
        self, voice_agent_id: str, page: int = 1, limit: int = 50
    ) -> Any:
        params = _clean({"page": page, "limit": limit})
        return await self._request(
            "GET", f"/api/voice-agents/{voice_agent_id}/sessions", params=params
        )

    async def get_voice_session(self, voice_session_id: str) -> Any:
        return await self._request("GET", f"/api/voice-sessions/{voice_session_id}")

    # --- conversation catalog ---
    # Shared with the workflow-level voice features; `capability=conversation` is
    # what narrows it to models a voice agent can actually use.
    async def list_voice_providers(self, capability: str = "conversation") -> Any:
        return await self._request(
            "GET", "/api/voice/providers", params={"capability": capability}
        )

    async def list_voice_provider_models(
        self, provider: str, capability: str = "conversation"
    ) -> Any:
        return await self._request(
            "GET",
            f"/api/voice/providers/{provider}/models",
            params={"capability": capability},
        )

    async def list_provider_system_voices(self, provider: str) -> Any:
        return await self._request(
            "GET", f"/api/voice/providers/{provider}/system-voices"
        )


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _extract_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except Exception:
        pass
    return resp.text or resp.reason_phrase
