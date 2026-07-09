from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .action_registry import api_action_spec, api_action_specs
from .api_v1 import dispatch as api_v1_dispatch
from .config import Settings
from .responses import ok


class ApiV2DispatchRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""
    client: str = ""


def actions_catalog() -> dict:
    """Return schema-rich action definitions for API v2 clients."""
    actions = [spec.v2_entry() for spec in api_action_specs()]
    return ok(
        {
            "version": "v2",
            "compatibility": {"v1_envelope": True, "dispatch_backend": "api_v1"},
            "actions": actions,
            "count": len(actions),
        },
        f"已返回 {len(actions)} 个 API v2 动作说明。",
        "returned api v2 actions",
    )


def dispatch(
    settings: Settings,
    action: str,
    params: dict | None = None,
    request_id: str = "",
    client: str = "",
) -> dict:
    """Dispatch through the stable v1 backend and add v2 policy/trace metadata."""
    normalized = action.strip().lower().replace("-", "_")
    spec = api_action_spec(normalized)
    result = api_v1_dispatch(settings, normalized, params or {}, request_id)
    result["api_version"] = "v2"
    result["policy"] = spec.v2_entry()["policy"] if spec else {"default": "deny", "risk": "unknown"}
    result["trace"] = {
        "client": client,
        "requested_action": action,
        "normalized_action": normalized,
        "backend": "api_v1",
    }
    return result
