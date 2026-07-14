import pytest

from assemblix_mcp.config import Settings, resolve_api_key


def _settings(**over):
    base = dict(api_url="http://x", api_key="sk_env", transport="stdio", host="h", port=1)
    base.update(over)
    return Settings(**base)


def test_resolve_prefers_header():
    assert resolve_api_key(_settings(), "Bearer sk_header") == "sk_header"


def test_resolve_falls_back_to_env():
    assert resolve_api_key(_settings(), None) == "sk_env"


def test_resolve_raises_without_any_key():
    with pytest.raises(ValueError):
        resolve_api_key(_settings(api_key=None), None)
