"""Thin async HTTP client over the Assemblix REST API.

Wire contract: query params are snake_case; request bodies are camelCase;
responses are camelCase. ``project_id`` is injected only where the endpoint
expects it (workflows list query + create body). Id-addressed and key-scoped
endpoints do not need it.
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
    def __init__(self, base_url: str, api_key: str, project_id: str) -> None:
        self._base = base_url.rstrip("/")
        self._project_id = project_id
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

    # --- workflows ---
    async def list_workflows(
        self,
        is_active: bool | None = None,
        is_published: bool | None = None,
        is_template: bool | None = None,
    ) -> Any:
        params = _clean(
            {
                "project_id": self._project_id,
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
                "projectId": self._project_id,
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


async def fetch_project_id(base_url: str, api_key: str) -> str:
    """Resolve the key's project via the whoami endpoint."""
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}"},
    ) as http:
        resp = await http.get("/api/api-keys/whoami")
    if resp.status_code >= 400:
        raise AssemblixAPIError(resp.status_code, _extract_detail(resp))
    return str(resp.json()["projectId"])


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
