from __future__ import annotations

from fastapi.testclient import TestClient

from xiaozhi_desktop_mcp.http_server import app


def test_http_exposes_api_v1_only():
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/actions").status_code == 200
    assert client.post("/tools/desktop/ask-cc", json={}).status_code == 404
