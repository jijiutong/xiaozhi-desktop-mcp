"""HTTP adapter for language-neutral Xiaozhi Desktop MCP clients."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_v1 import actions_catalog as api_v1_actions_catalog, api_health as api_v1_health, dispatch as api_v1_dispatch
from .api_v2 import (
    ApiV2DispatchRequest,
    actions_catalog as api_v2_actions_catalog,
    dispatch as api_v2_dispatch,
)
from .config import load_settings

app = FastAPI(title="Xiaozhi Desktop MCP HTTP Adapter")
settings = load_settings()
logger = logging.getLogger(__name__)

_PROTECTED_PREFIXES = ("/api/",)


class ApiV1DispatchRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""


@app.middleware("http")
async def require_auth_token(request: Request, call_next):
    started_at = time.monotonic()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    client_host = request.client.host if request.client else ""
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if token and request.url.path.startswith(_PROTECTED_PREFIXES):
        auth_header = request.headers.get("authorization", "")
        header_token = request.headers.get("x-desktop-mcp-token", "")
        if not _is_authorized(auth_header, header_token, token):
            response = JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "request_id": request_id,
                    "error": "unauthorized",
                    "error_spoken_message": "桌面 MCP 认证失败。",
                },
            )
            response.headers["X-Request-Id"] = request_id
            _log_http_request(request, response.status_code, started_at, request_id, client_host, authorized=False)
            return response
    try:
        response = await call_next(request)
    except Exception:
        _log_http_request(request, 500, started_at, request_id, client_host, authorized=not token)
        logger.exception(
            "desktop_mcp_http_exception request_id=%s method=%s path=%s client=%s",
            request_id,
            request.method,
            request.url.path,
            client_host,
        )
        raise
    response.headers["X-Request-Id"] = request_id
    _log_http_request(request, response.status_code, started_at, request_id, client_host, authorized=True)
    return response


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


@app.get("/api/v2/actions")
def http_api_v2_actions() -> dict:
    """Return schema-rich API v2 action metadata."""
    return api_v2_actions_catalog()


@app.post("/api/v2/dispatch")
def http_api_v2_dispatch(req: ApiV2DispatchRequest) -> dict:
    """API v2 dispatch with policy and trace metadata around the stable v1 backend."""
    return api_v2_dispatch(settings, req.action, req.params, req.request_id, req.client)


def main() -> None:
    host = os.getenv("DESKTOP_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("DESKTOP_MCP_HTTP_PORT", "8765"))
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if not token and not _is_loopback_host(host):
        raise SystemExit(
            "DESKTOP_MCP_AUTH_TOKEN is required when DESKTOP_MCP_HTTP_HOST is not localhost/127.0.0.1/::1"
        )
    uvicorn.run("xiaozhi_desktop_mcp.http_server:app", host=host, port=port)


def _is_authorized(auth_header: str, header_token: str, token: str) -> bool:
    return auth_header == f"Bearer {token}" or header_token == token


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"localhost", "127.0.0.1", "::1"}


def _log_http_request(
    request: Request,
    status_code: int,
    started_at: float,
    request_id: str,
    client_host: str,
    *,
    authorized: bool,
) -> None:
    cost_ms = int((time.monotonic() - started_at) * 1000)
    log_method = logger.warning if status_code >= 400 else logger.info
    log_method(
        "desktop_mcp_http request_id=%s method=%s path=%s status=%s cost_ms=%s client=%s authorized=%s",
        request_id,
        request.method,
        request.url.path,
        status_code,
        cost_ms,
        client_host,
        authorized,
    )


if __name__ == "__main__":
    main()
