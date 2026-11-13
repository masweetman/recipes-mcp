import pytest
import respx
from starlette.testclient import TestClient

from recipes_mcp.config import Settings
from recipes_mcp.server import build_server

from .test_security import resolve_to

TOKEN = "a" * 40
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture
def client(tmp_path):
    blogs = tmp_path / "blogs.yaml"
    blogs.write_text("blogs:\n  - {name: Example, domain: example.com, search: wordpress}\n")
    settings = Settings(mcp_path_token=TOKEN, blogs_file=blogs, public_host="recipes.test")
    app = build_server(settings).streamable_http_app()
    with TestClient(app, base_url="http://recipes.test") as c:
        yield c


def test_healthz(client):
    assert client.get("/healthz").status_code == 200


@pytest.mark.parametrize("path", ["/", "/mcp", "/mcp/", "/mcp/wrong"])
def test_wrong_paths_404(client, path):
    assert client.post(path, json=INIT, headers=HEADERS).status_code == 404


def test_token_path_works_and_lists_tools(client):
    r = client.post(f"/mcp/{TOKEN}", json=INIT, headers=HEADERS)
    assert r.status_code == 200
    r = client.post(
        f"/mcp/{TOKEN}", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=HEADERS
    )
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"list_sites", "search_recipes", "get_recipe"}


def test_get_recipe_off_allowlist_is_tool_error(client):
    body = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_recipe", "arguments": {"url": "http://127.0.0.1/"}}}
    r = client.post(f"/mcp/{TOKEN}", json=body, headers=HEADERS)
    assert r.json()["result"]["isError"] is True


@respx.mock
def test_shared_http_client_survives_multiple_requests(client, monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")
    ld = '{"@context":"https://schema.org","@type":"Recipe","name":"Pie","recipeIngredient":["egg"],"recipeInstructions":"Bake."}'
    respx.get("https://example.com/pie").respond(
        200,
        text=f'<html><script type="application/ld+json">{ld}</script></html>',
        headers={"content-type": "text/html"},
    )
    body = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_recipe", "arguments": {"url": "https://example.com/pie"}}}
    for _ in range(2):
        r = client.post(f"/mcp/{TOKEN}", json=body, headers=HEADERS)
        assert r.json()["result"]["isError"] is False


def test_weak_token_rejected():
    with pytest.raises(ValueError):
        Settings(mcp_path_token="short")
