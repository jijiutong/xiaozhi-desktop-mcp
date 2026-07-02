"""HTTP adapter for language-neutral Xiaozhi Desktop MCP clients."""

from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_v1 import actions_catalog as api_v1_actions_catalog, api_health as api_v1_health, dispatch as api_v1_dispatch
from .config import load_settings

app = FastAPI(title="Xiaozhi Desktop MCP HTTP Adapter")
settings = load_settings()

_PROTECTED_PREFIXES = ("/api/",)


class ApiV1DispatchRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""


@app.middleware("http")
async def require_auth_token(request: Request, call_next):
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if token and request.url.path.startswith(_PROTECTED_PREFIXES):
        auth_header = request.headers.get("authorization", "")
        header_token = request.headers.get("x-desktop-mcp-token", "")
        if auth_header != f"Bearer {token}" and header_token != token:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "unauthorized",
                    "error_spoken_message": "桌面 MCP 认证失败。",
                },
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, Any]:
    """Simple unauthenticated health check for local process monitors."""
    return {
        "success": True,
        "service": "xiaozhi-desktop-mcp",
        "message": "healthy",
        "spoken_message": "桌面 MCP 服务运行正常。",
    }


@app.get("/api/v1/health")
def http_api_v1_health() -> dict:
    """Language-agnostic structured health endpoint."""
    return api_v1_health(settings)


@app.get("/api/v1/actions")
def http_api_v1_actions() -> dict:
    """Return machine-friendly API v1 action metadata."""
    return api_v1_actions_catalog()


@app.post("/api/v1/dispatch")
def http_api_v1_dispatch(req: ApiV1DispatchRequest) -> dict:
    """Language-agnostic dispatch endpoint for Java, Python, Go, and other clients."""
    return api_v1_dispatch(settings, req.action, req.params, req.request_id)


def main() -> None:
    host = os.getenv("DESKTOP_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("DESKTOP_MCP_HTTP_PORT", "8765"))
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if not token and not _is_loopback_host(host):
        raise SystemExit(
            "DESKTOP_MCP_AUTH_TOKEN is required when DESKTOP_MCP_HTTP_HOST is not localhost/127.0.0.1/::1"
        )
    uvicorn.run("xiaozhi_desktop_mcp.http_server:app", host=host, port=port)


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"localhost", "127.0.0.1", "::1"}


if __name__ == "__main__":
    main()
