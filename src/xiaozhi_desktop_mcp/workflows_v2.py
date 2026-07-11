from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .action_registry import api_action_spec
from .config import Settings
from .responses import fail, ok
from .storage import PendingActionStore, WorkflowStore
from .validation import validate_params

WorkflowDispatcher = Callable[[Settings, str, dict, str, str], dict]
_FINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_FORBIDDEN_STEP_ACTIONS = frozenset({"pending_confirm"})


def plan_workflow(settings: Settings, name: str, steps: list[dict]) -> dict:
    if not steps:
        return fail("workflow steps are empty", "工作流至少需要一个步骤。")
    if len(steps) > 20:
        return fail("workflow exceeds 20 steps", "单个工作流最多支持 20 个步骤。")
    planned_steps = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            return fail(f"workflow step {index} must be an object", f"工作流第 {index + 1} 步格式不正确。")
        action = str(raw_step.get("action", "")).strip().lower().replace("-", "_")
        if action.startswith("workflow_") or action in _FORBIDDEN_STEP_ACTIONS:
            return fail("workflow step action is not allowed", "工作流里不能嵌套工作流控制或确认动作。")
        spec = api_action_spec(action)
        if spec is None:
            return fail(f"unknown workflow action: {action}", f"工作流第 {index + 1} 步动作不存在。")
        params = raw_step.get("params", {})
        if not isinstance(params, dict):
            return fail(f"workflow step {index} params must be an object", f"工作流第 {index + 1} 步参数不正确。")
        errors = validate_params(spec.v2_entry()["param_schema"], params)
        if errors:
            return fail(
                f"invalid workflow step {index}: {action}",
                f"工作流第 {index + 1} 步参数校验失败。",
                {"step_index": index, "validation_errors": errors},
            )
        planned_steps.append(
            {
                "index": index,
                "action": action,
                "params": params,
                "risk": spec.risk,
                "policy": spec.v2_entry()["policy"],
                "status": "planned",
            }
        )
    workflow_id = uuid4().hex[:16]
    workflow = WorkflowStore(settings).create(workflow_id, name.strip() or "Desktop workflow", planned_steps)
    return ok(
        {"workflow": workflow},
        f"工作流计划已创建，共 {len(planned_steps)} 步。",
        "planned workflow",
    )


def execute_workflow(settings: Settings, workflow_id: str, dispatcher: WorkflowDispatcher) -> dict:
    store = WorkflowStore(settings)
    workflow = store.get(workflow_id.strip())
    if not workflow:
        return fail("workflow not found", "没有找到这个工作流。")
    if workflow["status"] == "cancelled":
        return fail("workflow is cancelled", "这个工作流已经取消。")
    if workflow["status"] == "failed":
        return fail("workflow has failed", "这个工作流已经失败。")
    if workflow["status"] == "completed":
        return ok({"workflow": workflow}, "这个工作流已经执行完成。", "workflow already completed")
    claimed, previous_status, claim_error = store.claim_execution(workflow_id.strip())
    if not claimed:
        return fail("workflow not found", "没有找到这个工作流。")
    if claim_error:
        return fail(f"workflow is already {claim_error}", "这个工作流正在执行或已经结束。")
    workflow = claimed

    steps = workflow["steps"]
    current = int(workflow["current_step"])
    if previous_status == "waiting_confirmation":
        resumed = _resume_confirmed_step(settings, workflow)
        if isinstance(resumed, dict) and resumed.get("success") is False:
            return resumed
        if resumed is None:
            workflow = store.update(
                workflow_id,
                status="waiting_confirmation",
                steps=steps,
                current_step=current,
            ) or workflow
            return ok({"workflow": workflow}, "工作流仍在等待确认。", "workflow waiting for confirmation")
        steps, current = resumed

    workflow = store.update(workflow_id, status="running", steps=steps, current_step=current) or workflow
    steps = workflow["steps"]
    while current < len(steps):
        step = steps[current]
        step["status"] = "running"
        store.update(workflow_id, status="running", steps=steps, current_step=current)
        result = dispatcher(
            settings,
            str(step["action"]),
            dict(step.get("params", {})),
            f"workflow-{workflow_id}-{current}",
            f"workflow:{workflow_id}",
        )
        step["result"] = _result_summary(result)
        latest = store.get(workflow_id)
        if latest and latest["status"] == "cancelled":
            return fail(
                "workflow was cancelled during execution",
                "工作流已取消，不再执行后续步骤。",
                {"workflow": latest},
            )
        pending = result.get("data", {}).get("action") if isinstance(result.get("data"), dict) else None
        if result.get("success") and isinstance(pending, dict) and pending.get("status") == "pending":
            step["status"] = "waiting_confirmation"
            step["pending_action_id"] = pending.get("action_id", "")
            workflow = store.update(
                workflow_id,
                status="waiting_confirmation",
                steps=steps,
                current_step=current,
            ) or workflow
            return ok(
                {"workflow": workflow},
                f"工作流第 {current + 1} 步等待确认。",
                "workflow waiting for confirmation",
            )
        if not result.get("success"):
            step["status"] = "failed"
            workflow = store.update(workflow_id, status="failed", steps=steps, current_step=current) or workflow
            return fail(
                f"workflow step failed: {step['action']}",
                f"工作流第 {current + 1} 步执行失败。",
                {"workflow": workflow},
            )
        step["status"] = "completed"
        current += 1
        store.update(workflow_id, status="running", steps=steps, current_step=current)

    workflow = store.update(workflow_id, status="completed", steps=steps, current_step=current) or workflow
    return ok({"workflow": workflow}, "工作流执行完成。", "workflow completed")


def get_workflow(settings: Settings, workflow_id: str) -> dict:
    workflow = WorkflowStore(settings).get(workflow_id.strip())
    if not workflow:
        return fail("workflow not found", "没有找到这个工作流。")
    return ok({"workflow": workflow}, "已返回工作流状态。", "returned workflow")


def cancel_workflow(settings: Settings, workflow_id: str) -> dict:
    store = WorkflowStore(settings)
    before = store.get(workflow_id.strip())
    if not before:
        return fail("workflow not found", "没有找到这个工作流。")
    if before["status"] in _FINAL_STATUSES:
        return fail(f"workflow is already {before['status']}", "这个工作流已经结束。")
    workflow = store.cancel(workflow_id.strip()) or before
    return ok({"workflow": workflow}, "工作流已取消。", "cancelled workflow")


def _resume_confirmed_step(settings: Settings, workflow: dict) -> tuple[list[dict], int] | dict | None:
    steps = workflow["steps"]
    current = int(workflow["current_step"])
    if current >= len(steps):
        return steps, current
    pending_id = str(steps[current].get("pending_action_id", ""))
    pending = PendingActionStore(settings).get(pending_id)
    if not pending or pending["status"] in {"pending", "executing"}:
        return None
    if pending["status"] != "completed":
        steps[current]["status"] = "failed"
        workflow = WorkflowStore(settings).update(
            workflow["workflow_id"], status="failed", steps=steps, current_step=current
        ) or workflow
        return fail(
            f"pending action ended with status: {pending['status']}",
            "待确认动作没有成功，工作流已停止。",
            {"workflow": workflow},
        )
    steps[current]["status"] = "completed"
    steps[current]["confirmed_result"] = {
        "success": bool((pending.get("result") or {}).get("success")),
        "status": pending["status"],
    }
    return steps, current + 1


def _result_summary(result: dict[str, Any]) -> dict:
    return {
        "success": bool(result.get("success")),
        "action": result.get("action", ""),
        "request_id": result.get("request_id", ""),
        "error_code": result.get("error_code", ""),
        "error": result.get("error", ""),
    }
