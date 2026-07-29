from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from pydantic import BaseModel, Field

from .action_registry import api_action_spec, api_action_specs, required_scope
from .api_v1 import dispatch as api_v1_dispatch
from .config import Settings
from .responses import ok
from .storage import WorkflowStore, record_audit_event
from .validation import validate_params

logger = logging.getLogger(__name__)


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
    authorized_scopes: frozenset[str] | None = None,
) -> dict:
    """Dispatch through the stable v1 backend and add v2 policy/trace metadata."""
    started_at = time.monotonic()
    normalized = action.strip().lower().replace("-", "_")
    spec = api_action_spec(normalized)
    if spec is None:
        result = _v2_error(
            normalized or action,
            request_id,
            client,
            "UNKNOWN_ACTION",
            f"unknown action: {action}",
            "未知动作，我没有执行。",
        )
        _audit(settings, result, client, {}, started_at)
        return result
    clean_params = dict(params or {})
    required_scopes = (
        required_scopes_for_request(settings, normalized, clean_params)
        if authorized_scopes is not None and "*" not in authorized_scopes
        else frozenset({required_scope(normalized)})
    )
    missing_scopes = _missing_scopes(required_scopes, authorized_scopes)
    if missing_scopes:
        missing_scope = sorted(missing_scopes)[0]
        result = _v2_error(
            normalized,
            request_id,
            client,
            "SCOPE_DENIED",
            f"required scope is missing: {missing_scope}",
            "客户端没有执行这个桌面动作的权限。",
            {"required_scope": missing_scope, "required_scopes": sorted(required_scopes)},
            spec.v2_entry()["policy"],
        )
        _audit(settings, result, client, clean_params, started_at)
        return result
    validation_errors = validate_params(spec.v2_entry()["param_schema"], clean_params)
    if validation_errors:
        result = _v2_error(
            normalized,
            request_id,
            client,
            "INVALID_PARAMS",
            f"invalid params for action {normalized}",
            "参数不完整或格式不对，我没有执行。",
            {"validation_errors": validation_errors},
            spec.v2_entry()["policy"],
        )
        _audit(settings, result, client, clean_params, started_at)
        return result
    if spec.v2_entry()["policy"].get("default") == "pending":
        clean_params.pop("confirm", None)
    result = api_v1_dispatch(settings, normalized, clean_params, request_id)
    result["api_version"] = "v2"
    if not result.get("success"):
        result["error_code"] = _execution_error_code(str(result.get("error", "")))
    result["policy"] = spec.v2_entry()["policy"] if spec else {"default": "deny", "risk": "unknown"}
    result["trace"] = {
        "client": client,
        "requested_action": action,
        "normalized_action": normalized,
        "backend": "api_v1",
    }
    _audit(settings, result, client, clean_params, started_at)
    return result


def required_scopes_for_request(settings: Settings, action: str, params: dict | None = None) -> frozenset[str]:
    """Resolve top-level and nested scopes for composite API requests."""
    normalized = action.strip().lower().replace("-", "_")
    clean_params = params if isinstance(params, dict) else {}
    scopes = _embedded_action_scopes(normalized, clean_params)
    if normalized == "workflow_plan":
        scopes.update(_workflow_step_scopes(clean_params.get("steps", [])))
    elif normalized == "workflow_execute":
        workflow_id = str(clean_params.get("workflow_id", "")).strip()
        workflow = WorkflowStore(settings).get(workflow_id) if workflow_id else None
        if workflow:
            scopes.update(_workflow_step_scopes(workflow.get("steps", [])))
    return frozenset(scopes)


def _missing_scopes(required: frozenset[str], authorized: frozenset[str] | None) -> frozenset[str]:
    if authorized is None or "*" in authorized:
        return frozenset()
    return required - authorized


def _embedded_action_scopes(action: str, params: dict) -> set[str]:
    scopes = {required_scope(action)}
    if action != "desktop_intent":
        return scopes
    category = str(params.get("category", "")).strip().lower()
    intent = str(params.get("intent", "")).strip().lower()
    nested_scope = _INTENT_READ_SCOPES.get((category, intent))
    if nested_scope:
        scopes.add(nested_scope)
    return scopes


def _workflow_step_scopes(raw_steps: Any) -> set[str]:
    scopes: set[str] = set()
    if not isinstance(raw_steps, list):
        return scopes
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        if str(raw_step.get("kind", "action")).strip().lower() == "condition":
            for branch_name in ("then", "else"):
                branch = raw_step.get(branch_name)
                if isinstance(branch, dict):
                    scopes.update(
                        _embedded_action_scopes(
                            str(branch.get("action", "")).strip().lower().replace("-", "_"),
                            branch.get("params", {}) if isinstance(branch.get("params"), dict) else {},
                        )
                    )
        else:
            scopes.update(
                _embedded_action_scopes(
                    str(raw_step.get("action", "")).strip().lower().replace("-", "_"),
                    raw_step.get("params", {}) if isinstance(raw_step.get("params"), dict) else {},
                )
            )
        compensation = raw_step.get("compensation")
        if isinstance(compensation, dict):
            scopes.update(
                _embedded_action_scopes(
                    str(compensation.get("action", "")).strip().lower().replace("-", "_"),
                    compensation.get("params", {}) if isinstance(compensation.get("params"), dict) else {},
                )
            )
    return scopes


_INTENT_READ_SCOPES = {
    ("desktop", "screenshot"): "screen:read",
    ("desktop", "window_screenshot"): "screen:read",
    ("desktop", "ocr"): "screen:read",
    ("desktop", "observe"): "screen:read",
    ("desktop", "ui_tree"): "screen:read",
    ("desktop", "capabilities"): "screen:read",
    ("browser", "tabs"): "screen:read",
    ("browser", "current"): "screen:read",
}


def _execution_error_code(error: str) -> str:
    normalized = error.lower()
    desktop_execution_codes = {
        "recovery required": "RECOVERY_REQUIRED",
        "observation expired": "OBSERVATION_EXPIRED",
        "window changed": "WINDOW_CHANGED",
        "target stale": "TARGET_STALE",
        "target ambiguous": "TARGET_AMBIGUOUS",
        "precondition failed": "PRECONDITION_FAILED",
        "expectation timeout": "EXPECTATION_TIMEOUT",
        "retry exhausted": "RETRY_EXHAUSTED",
    }
    for marker, code in desktop_execution_codes.items():
        if marker in normalized:
            return code
    if "timed out" in normalized or "timeout" in normalized:
        return "TIMEOUT"
    permission_markers = (
        "permission",
        "not allowed to send keystrokes",
        "not allowed assistive access",
        "不允许发送按键",
        "不允许辅助访问",
        "1002",
        "-25211",
    )
    if any(marker in normalized for marker in permission_markers):
        return "PERMISSION_DENIED"
    if any(
        marker in normalized
        for marker in ("allowlist", "allowed base", "only http", "credentials are not allowed", "domain is not")
    ):
        return "POLICY_DENIED"
    if "not found" in normalized:
        return "NOT_FOUND"
    if "already" in normalized:
        return "CONFLICT"
    if "invalid" in normalized or "required" in normalized or "empty" in normalized:
        return "INVALID_PARAMS"
    return "EXECUTION_FAILED"


def _audit(settings: Settings, result: dict, client: str, params: dict, started_at: float) -> None:
    try:
        record_audit_event(
            settings,
            request_id=str(result.get("request_id", "")),
            client=client,
            action=str(result.get("action", "")),
            success=bool(result.get("success")),
            error_code=str(result.get("error_code", "")),
            cost_ms=int((time.monotonic() - started_at) * 1000),
            param_keys=list(params),
        )
    except (OSError, sqlite3.Error):
        logger.warning("desktop_mcp_audit_write_failed action=%s", result.get("action", ""), exc_info=True)


def _v2_error(
    action: str,
    request_id: str,
    client: str,
    error_code: str,
    error: str,
    spoken: str,
    data: dict | None = None,
    policy: dict | None = None,
) -> dict:
    return {
        "success": False,
        "request_id": request_id,
        "action": action,
        "spoken_message": "",
        "error_spoken_message": spoken,
        "error": error,
        "error_code": error_code,
        "data": data or {},
        "api_version": "v2",
        "policy": policy or {"default": "deny", "risk": "unknown"},
        "trace": {
            "client": client,
            "requested_action": action,
            "normalized_action": action,
            "backend": "validation",
        },
    }
