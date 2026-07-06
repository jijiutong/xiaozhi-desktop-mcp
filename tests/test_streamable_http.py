from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from xiaozhi_desktop_mcp.server import StreamableHTTPAuthAndLoggingMiddleware, _is_loopback_host


async def ok(_request):
    return JSONResponse({"ok": True})


def test_streamable_http_middleware_requires_token():
    app = StreamableHTTPAuthAndLoggingMiddleware(Starlette(routes=[Route("/mcp", ok)]), "secret")
    client = TestClient(app)

    response = client.get("/mcp")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.headers["x-request-id"]


def test_streamable_http_middleware_accepts_bearer_token():
    app = StreamableHTTPAuthAndLoggingMiddleware(Starlette(routes=[Route("/mcp", ok)]), "secret")
    client = TestClient(app)

    response = client.get("/mcp", headers={"Authorization": "Bearer secret", "X-Request-Id": "req-stream"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["x-request-id"] == "req-stream"


def test_streamable_http_middleware_accepts_desktop_token_header():
    app = StreamableHTTPAuthAndLoggingMiddleware(Starlette(routes=[Route("/mcp", ok)]), "secret")
    client = TestClient(app)

    response = client.get("/mcp", headers={"X-Desktop-Mcp-Token": "secret"})

    assert response.status_code == 200


def test_streamable_http_non_localhost_detection():
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
