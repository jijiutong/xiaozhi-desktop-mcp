from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .action_registry import api_action_spec, workflow_replay_safe
from .config import Settings
from .responses import fail, ok
from .storage import PendingActionStore, WorkflowStore
from .validation import validate_params

WorkflowDispatcher = Callable[[Settings, str, dict, str, str], dict]
_FINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_FORBIDDEN_STEP_ACTIONS = frozenset({"pending_create", "pending_confirm", "pending_cancel"})


def plan_workflow(settings: Settings, name: str, steps: list[dict]) -> dict:
    if not steps:
        return fail("workflow steps are empty", "工作流至少需要一个步骤。")
    if len(steps) > 20:
        return fail("workflow exceeds 20 steps", "单个工作流最多支持 20 个步骤。")
    planned_steps = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            return fail(f"workflow step {index} must be an object", f"工作流第 {index + 1} 步格式不正确。")
        kind = str(raw_step.get("kind", "action")).strip().lower()
        if kind not in {"action", "wait", "condition"}:
            return fail(f"unsupported workflow step kind: {kind}", f"工作流第 {index + 1} 步类型不支持。")
        if kind == "condition":
            condition_step = _validated_condition_step(raw_step, index)
            if condition_step.get("success") is False:
                return condition_step
            planned_steps.append(condition_step)
            continue
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
        if kind == "wait":
            wait_step = _validated_wait_step(raw_step, spec, index, action, params)
            if wait_step.get("success") is False:
                return wait_step
            planned_steps.append(wait_step)
            continue
        retry = raw_step.get("retry", {})
        if not isinstance(retry, dict):
            return fail("workflow retry must be an object", f"工作流第 {index + 1} 步重试配置不正确。")
        try:
            max_attempts = int(retry.get("max_attempts", 1))
        except (TypeError, ValueError):
            return fail("workflow max_attempts must be an integer", f"工作流第 {index + 1} 步重试次数不正确。")
        if not 1 <= max_attempts <= 3:
            return fail("workflow max_attempts must be between 1 and 3", "工作流单步最多尝试 3 次。")
        if max_attempts > 1 and not workflow_replay_safe(action):
            return fail("only read-only workflow steps can retry", "只有显式只读的工作流步骤可以自动重试。")
        compensation = _validated_compensation(raw_step.get("compensation"), index)
        if isinstance(compensation, dict) and compensation.get("success") is False:
            return compensation
        planned_compensation = compensation if isinstance(compensation, dict) else None
        planned_steps.append(
            {
                "index": index,
                "kind": "action",
                "action": action,
                "params": params,
                "risk": spec.risk,
                "policy": spec.v2_entry()["policy"],
                "status": "planned",
                "retry": {"max_attempts": max_attempts},
                "attempts": 0,
                **({"compensation": planned_compensation} if planned_compensation else {}),
            }
        )
    workflow_id = uuid4().hex[:16]
    store = WorkflowStore(settings)
    workflow = store.create(workflow_id, name.strip() or "Desktop workflow", planned_steps)
    store.append_event(workflow_id, "planned", details={"step_count": len(planned_steps)})
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
    claimed, previous_status, claim_error, run_token = store.claim_execution(workflow_id.strip())
    if not claimed:
        return fail("workflow not found", "没有找到这个工作流。")
    if claim_error:
        return fail(f"workflow is already {claim_error}", "这个工作流正在执行或已经结束。")
    workflow = claimed
    steps = workflow["steps"]
    current = int(workflow["current_step"])
    if previous_status == "recovering":
        interrupted = steps[current] if current < len(steps) else None
        if isinstance(interrupted, dict) and interrupted.get("status") == "running":
            action = str(interrupted.get("action", ""))
            uncertain_action = action
            uncertain_phase = "action"
            compensation = interrupted.get("compensation")
            if isinstance(compensation, dict) and compensation.get("status") == "compensating":
                uncertain_action = str(compensation.get("action", ""))
                uncertain_phase = "compensation"
            if not workflow_replay_safe(uncertain_action):
                interrupted["status"] = "failed"
                interrupted["result"] = _result_summary(
                    fail(
                        "workflow recovery required: write step outcome is unknown",
                        "上次写操作的结果不确定，工作流已停止，避免重复执行。",
                    )
                )
                workflow = store.update(
                    workflow_id,
                    status="failed",
                    steps=steps,
                    current_step=current,
                    run_token=run_token,
                ) or workflow
                store.append_event(
                    workflow_id,
                    "recovery_blocked",
                    step_index=current,
                    details={
                        "action": uncertain_action,
                        "phase": uncertain_phase,
                        "reason": "unknown_write_outcome",
                    },
                )
                return fail(
                    "workflow recovery required: write step outcome is unknown",
                    "上次写操作的结果不确定，工作流已停止，避免重复执行。",
                    {"workflow": workflow},
                )
            interrupted["status"] = "planned"
        store.append_event(
            workflow_id,
            "recovered",
            step_index=current,
            details={"strategy": "replay_read_only" if interrupted else "resume_terminal_transition"},
        )
    else:
        store.append_event(
            workflow_id,
            "started" if previous_status == "planned" else "resumed",
            step_index=current,
        )

    if previous_status == "waiting_confirmation":
        resumed = _resume_confirmed_step(settings, workflow, store, run_token)
        if isinstance(resumed, dict) and resumed.get("success") is False:
            return resumed
        if resumed is None:
            workflow = store.update(
                workflow_id,
                status="waiting_confirmation",
                steps=steps,
                current_step=current,
                run_token=run_token,
            ) or workflow
            return ok({"workflow": workflow}, "工作流仍在等待确认。", "workflow waiting for confirmation")
        steps, current = resumed
        store.append_event(
            workflow_id,
            "step_completed",
            step_index=current - 1,
            details={"action": str(steps[current - 1].get("action", "")), "confirmed": True},
        )

    workflow = store.update(
        workflow_id,
        status="running",
        steps=steps,
        current_step=current,
        run_token=run_token,
    ) or workflow
    steps = workflow["steps"]
    while current < len(steps):
        step = steps[current]
        if step.get("kind") == "wait" and step.get("next_poll_at"):
            next_poll_at = datetime.fromisoformat(str(step["next_poll_at"]))
            if datetime.now(timezone.utc) < next_poll_at:
                workflow = store.update(
                    workflow_id,
                    status="waiting_condition",
                    steps=steps,
                    current_step=current,
                    run_token=run_token,
                ) or workflow
                store.append_event(workflow_id, "waiting_condition", step_index=current)
                return ok(
                    {"workflow": workflow},
                    f"工作流第 {current + 1} 步仍在等待条件。",
                    "workflow waiting for condition",
                )
            step.pop("next_poll_at", None)
        if step.get("kind") == "condition" and not step.get("selected_branch"):
            selected = "then" if _workflow_condition_satisfied(steps, dict(step.get("if", {}))) else "else"
            branch = dict(step[selected])
            step["selected_branch"] = selected
            step["action"] = branch["action"]
            step["params"] = branch.get("params", {})
            step["risk"] = branch["risk"]
            step["policy"] = branch["policy"]
        step["status"] = "running"
        step["attempts"] = int(step.get("attempts", 0)) + 1
        store.update(
            workflow_id,
            status="running",
            steps=steps,
            current_step=current,
            run_token=run_token,
        )
        result = dispatcher(
            settings,
            str(step["action"]),
            dict(step.get("params", {})),
            f"workflow-{workflow_id}-{current}",
            f"workflow:{workflow_id}",
        )
        step["result"] = _result_summary(result)
        if step.get("kind") == "wait" and result.get("success"):
            if _wait_condition_satisfied(result, dict(step.get("until", {}))):
                step["wait_satisfied"] = True
            elif int(step.get("attempts", 1)) < int(step.get("max_attempts", 1)):
                step["status"] = "waiting_condition"
                interval_ms = int(step.get("interval_ms", 0))
                step["next_poll_at"] = (
                    datetime.now(timezone.utc) + timedelta(milliseconds=interval_ms)
                ).isoformat()
                workflow = store.update(
                    workflow_id,
                    status="waiting_condition",
                    steps=steps,
                    current_step=current,
                    run_token=run_token,
                ) or workflow
                store.append_event(workflow_id, "waiting_condition", step_index=current)
                return ok(
                    {"workflow": workflow},
                    f"工作流第 {current + 1} 步等待条件满足。",
                    "workflow waiting for condition",
                )
            else:
                result = fail("workflow wait condition timed out", "等待条件没有在限定次数内满足。")
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
                run_token=run_token,
            ) or workflow
            store.append_event(
                workflow_id,
                "waiting_confirmation",
                step_index=current,
                details={"action": str(step["action"])},
            )
            return ok(
                {"workflow": workflow},
                f"工作流第 {current + 1} 步等待确认。",
                "workflow waiting for confirmation",
            )
        if not result.get("success"):
            max_attempts = int(step.get("retry", {}).get("max_attempts", 1))
            if int(step.get("attempts", 1)) < max_attempts:
                step["status"] = "planned"
                store.update(
                    workflow_id,
                    status="running",
                    steps=steps,
                    current_step=current,
                    run_token=run_token,
                )
                continue
            compensation = step.get("compensation")
            if isinstance(compensation, dict):
                compensation["status"] = "compensating"
                store.update(
                    workflow_id,
                    status="running",
                    steps=steps,
                    current_step=current,
                    run_token=run_token,
                )
                compensation_result = dispatcher(
                    settings,
                    str(compensation["action"]),
                    dict(compensation.get("params", {})),
                    f"workflow-{workflow_id}-{current}-compensation",
                    f"workflow:{workflow_id}",
                )
                compensation["result"] = _result_summary(compensation_result)
                compensation["status"] = "completed" if compensation_result.get("success") else "failed"
            step["status"] = "failed"
            workflow = store.update(
                workflow_id,
                status="failed",
                steps=steps,
                current_step=current,
                run_token=run_token,
            ) or workflow
            store.append_event(
                workflow_id,
                "failed",
                step_index=current,
                details={"action": str(step["action"]), "error_code": str(result.get("error_code", ""))},
            )
            return fail(
                f"workflow step failed: {step['action']}",
                f"工作流第 {current + 1} 步执行失败。",
                {"workflow": workflow},
            )
        step["status"] = "completed"
        store.append_event(
            workflow_id,
            "step_completed",
            step_index=current,
            details={"action": str(step["action"])},
        )
        current += 1
        store.update(
            workflow_id,
            status="running",
            steps=steps,
            current_step=current,
            run_token=run_token,
        )

    workflow = store.update(
        workflow_id,
        status="completed",
        steps=steps,
        current_step=current,
        run_token=run_token,
    ) or workflow
    store.append_event(workflow_id, "completed", step_index=current)
    return ok({"workflow": workflow}, "工作流执行完成。", "workflow completed")


def get_workflow(settings: Settings, workflow_id: str) -> dict:
    store = WorkflowStore(settings)
    workflow = store.get(workflow_id.strip())
    if not workflow:
        return fail("workflow not found", "没有找到这个工作流。")
    return ok(
        {"workflow": workflow, "events": store.events(workflow_id.strip())},
        "已返回工作流状态。",
        "returned workflow",
    )


def cancel_workflow(settings: Settings, workflow_id: str) -> dict:
    store = WorkflowStore(settings)
    before = store.get(workflow_id.strip())
    if not before:
        return fail("workflow not found", "没有找到这个工作流。")
    if before["status"] in _FINAL_STATUSES:
        return fail(f"workflow is already {before['status']}", "这个工作流已经结束。")
    workflow = store.cancel(workflow_id.strip()) or before
    store.append_event(workflow_id.strip(), "cancelled", step_index=int(workflow["current_step"]))
    return ok({"workflow": workflow}, "工作流已取消。", "cancelled workflow")


def _resume_confirmed_step(
    settings: Settings,
    workflow: dict,
    store: WorkflowStore,
    run_token: str,
) -> tuple[list[dict], int] | dict | None:
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
        workflow = store.update(
            workflow["workflow_id"],
            status="failed",
            steps=steps,
            current_step=current,
            run_token=run_token,
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


def _validated_compensation(raw: Any, step_index: int) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return fail("workflow compensation must be an object", f"工作流第 {step_index + 1} 步补偿配置不正确。")
    action = str(raw.get("action", "")).strip().lower().replace("-", "_")
    params = raw.get("params", {})
    if not action or action.startswith("workflow_") or action in _FORBIDDEN_STEP_ACTIONS:
        return fail("workflow compensation action is not allowed", "工作流补偿动作不允许执行。")
    spec = api_action_spec(action)
    if spec is None or spec.risk != "low" or spec.pending_action_type:
        return fail("workflow compensation must be low risk", "工作流补偿只能使用无需确认的低风险动作。")
    if not isinstance(params, dict):
        return fail("workflow compensation params must be an object", "工作流补偿参数不正确。")
    errors = validate_params(spec.v2_entry()["param_schema"], params)
    if errors:
        return fail(
            "invalid workflow compensation params",
            f"工作流第 {step_index + 1} 步补偿参数校验失败。",
            {"step_index": step_index, "validation_errors": errors},
        )
    return {"action": action, "params": params, "status": "planned"}


def _validated_wait_step(raw: dict, spec: Any, step_index: int, action: str, params: dict) -> dict:
    if not workflow_replay_safe(action) or spec.pending_action_type:
        return fail("workflow wait action must be read-only", "工作流等待只能轮询显式只读动作。")
    until = raw.get("until", {})
    if not isinstance(until, dict) or "equals" not in until:
        return fail("workflow wait until must contain equals", "工作流等待条件格式不正确。")
    field = str(until.get("field", "")).strip()
    parts = field.split(".")
    if not field.startswith("data.") or any(not part.replace("_", "").isalnum() for part in parts):
        return fail("workflow wait field must be a data path", "工作流等待条件只能读取结构化 data 字段。")
    try:
        max_attempts = int(raw.get("max_attempts", 10))
        interval_ms = int(raw.get("interval_ms", 250))
    except (TypeError, ValueError):
        return fail("workflow wait limits must be integers", "工作流等待次数或间隔不正确。")
    if not 1 <= max_attempts <= 20:
        return fail("workflow wait max_attempts must be between 1 and 20", "工作流等待最多轮询 20 次。")
    if not 0 <= interval_ms <= 5000:
        return fail("workflow wait interval_ms must be between 0 and 5000", "工作流等待间隔不正确。")
    return {
        "index": step_index,
        "kind": "wait",
        "action": action,
        "params": params,
        "risk": spec.risk,
        "policy": spec.v2_entry()["policy"],
        "status": "planned",
        "until": {"field": field, "equals": until["equals"]},
        "max_attempts": max_attempts,
        "interval_ms": interval_ms,
        "attempts": 0,
    }


def _wait_condition_satisfied(result: dict, condition: dict) -> bool:
    current: Any = result
    for part in str(condition.get("field", "")).split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current == condition.get("equals")


def _validated_condition_step(raw: dict, step_index: int) -> dict:
    condition = raw.get("if", {})
    if not isinstance(condition, dict) or "equals" not in condition:
        return fail("workflow condition must contain equals", "工作流条件格式不正确。")
    try:
        source_step = int(condition.get("step", -1))
    except (TypeError, ValueError):
        return fail("workflow condition step must be an integer", "工作流条件引用的步骤不正确。")
    if source_step < 0 or source_step >= step_index:
        return fail("workflow condition must reference an earlier step", "工作流条件只能引用之前的步骤。")
    field = str(condition.get("field", "")).strip()
    if field not in {"status", "result.success", "result.error_code"}:
        return fail("workflow condition field is not allowed", "工作流条件字段不在允许范围内。")
    branches: dict[str, dict] = {}
    for branch_name in ("then", "else"):
        branch = raw.get(branch_name)
        if not isinstance(branch, dict):
            return fail("workflow condition branches must be objects", "工作流条件分支格式不正确。")
        action = str(branch.get("action", "")).strip().lower().replace("-", "_")
        if not action or action.startswith("workflow_") or action in _FORBIDDEN_STEP_ACTIONS:
            return fail("workflow condition branch action is not allowed", "工作流条件分支动作不允许执行。")
        spec = api_action_spec(action)
        params = branch.get("params", {})
        if spec is None:
            return fail(f"unknown workflow branch action: {action}", "工作流条件分支动作不存在。")
        if not isinstance(params, dict):
            return fail("workflow branch params must be an object", "工作流条件分支参数不正确。")
        errors = validate_params(spec.v2_entry()["param_schema"], params)
        if errors:
            return fail(
                "invalid workflow branch params",
                "工作流条件分支参数校验失败。",
                {"step_index": step_index, "branch": branch_name, "validation_errors": errors},
            )
        branches[branch_name] = {
            "action": action,
            "params": params,
            "risk": spec.risk,
            "policy": spec.v2_entry()["policy"],
        }
    return {
        "index": step_index,
        "kind": "condition",
        "if": {"step": source_step, "field": field, "equals": condition["equals"]},
        "then": branches["then"],
        "else": branches["else"],
        "status": "planned",
        "retry": {"max_attempts": 1},
        "attempts": 0,
    }


def _workflow_condition_satisfied(steps: list[dict], condition: dict) -> bool:
    source = steps[int(condition["step"])]
    current: Any = source
    for part in str(condition["field"]).split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current == condition.get("equals")
