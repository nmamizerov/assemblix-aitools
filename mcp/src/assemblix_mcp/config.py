"""Configuration and per-request API key resolution."""

from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    api_url: str
    api_key: str | None
    transport: str
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_url=os.environ.get("ASSEMBLIX_API_URL", "https://app.assmblx.com"),
            api_key=os.environ.get("ASSEMBLIX_API_KEY"),
            transport=os.environ.get("ASSEMBLIX_MCP_TRANSPORT", "stdio"),
            host=os.environ.get("ASSEMBLIX_MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("ASSEMBLIX_MCP_PORT", "8000")),
        )


def resolve_api_key(settings: Settings, header_value: str | None) -> str:
    """Return the bearer token, preferring an incoming Authorization header."""
    if header_value:
        token = header_value.removeprefix("Bearer ").strip()
        if token:
            return token
    if settings.api_key:
        return settings.api_key
    raise ValueError(
        "No API key: set ASSEMBLIX_API_KEY or send an Authorization: Bearer header."
    )
