from __future__ import annotations

import time
from typing import Any

from .config import Settings
from .observations import observe_desktop
from .responses import fail, ok
from .storage import IdempotencyStore, ObservationStore
from .tools.accessibility import accessibility_action

_TARGET_SIGNATURE_KEYS = ("role", "subrole", "title", "description", "identifier")
_ACTION_KEYS = frozenset(
    {"command", "target_element_id", "text", "direction", "amount", "path"}
)
_EXPECTATION_KINDS = frozenset(
    {"element_absent", "element_present", "element_enabled", "element_disabled", "tree_changed"}
)


def execute_desktop_step(
    settings: Settings,
    observation_id: str,
    target: dict[str, Any],
    preconditions: dict[str, Any],
    action: dict[str, Any],
    expectation: dict[str, Any] | None = None,
    idempotency_key: str = "",
    timeout_ms: int = 5000,
) -> dict:
    """Revalidate, execute once, and verify a semantic desktop action."""
    original = ObservationStore(settings).get(observation_id.strip())
    if not original:
        return fail("observation not found", "没有找到这次桌面观察，请重新观察。")
    if original.get("expired"):
        return fail("observation expired", "桌面观察已经过期，请重新观察。")
    if not isinstance(target, dict) or not isinstance(action, dict):
        return fail("target and action must be objects", "桌面操作目标或动作格式不正确。")
    if timeout_ms < 100 or timeout_ms > 30000:
        return fail("timeout_ms must be between 100 and 30000", "桌面操作超时时间不正确。")

    source_target = _find_source_target(original, target)
    if not source_target:
        return fail("target not found in observation", "目标元素不在原始观察中，请重新观察。")

    key = idempotency_key.strip()
    idempotency = IdempotencyStore(settings)
    if key:
        status, previous = idempotency.claim(key)
        if status in {"completed", "failed"} and previous is not None:
            return previous
        if status == "executing":
            return fail(
                "recovery required for in-flight idempotency key",
                "这个动作的上次执行状态不确定，需要人工检查后再继续。",
            )

    result = _execute_claimed_step(
        settings,
        original,
        source_target,
        preconditions,
        action,
        expectation or {},
        timeout_ms,
    )
    if key:
        idempotency.resolve(key, result)
    return result


def _execute_claimed_step(
    settings: Settings,
    original: dict[str, Any],
    source_target: dict[str, Any],
    preconditions: dict[str, Any],
    action: dict[str, Any],
    expectation: dict[str, Any],
    timeout_ms: int,
) -> dict:
    before = observe_desktop(
        settings,
        str(original.get("app", "")),
        int(original.get("window_index", 1)),
    )
    if not before.get("success"):
        return before
    if not _same_window(original, before):
        return fail("window changed", "窗口已经变化，我没有在新窗口上继续操作。")
    current_target, target_state = _locate_matching_target(before, source_target)
    if target_state == "ambiguous":
        return fail("target ambiguous", "界面里出现了多个相同目标，我没有猜测点击。")
    if not current_target:
        return fail("target stale", "界面已经变化，原目标不再唯一有效，请重新观察。")
    if not _preconditions_satisfied(current_target, preconditions):
        return fail("precondition failed", "目标元素不再满足执行前置条件，我没有操作。")

    command = str(action.get("command", "")).strip().lower().replace("-", "_")
    if not command:
        return fail("action command is required", "桌面操作缺少动作命令。")
    unknown_action_keys = sorted(set(action) - _ACTION_KEYS)
    if unknown_action_keys:
        return fail(
            f"unknown desktop step action params: {', '.join(unknown_action_keys)}",
            "桌面操作包含不支持的参数。",
        )
    target_element_id = str(action.get("target_element_id", ""))
    if command == "drag":
        secondary_source = _find_source_target(original, {"element_id": target_element_id})
        if not secondary_source:
            return fail("target stale", "拖拽终点不在原始观察中，请重新观察。")
        secondary_target, secondary_state = _locate_matching_target(before, secondary_source)
        if secondary_state == "ambiguous":
            return fail("target ambiguous", "界面里出现了多个相同拖拽终点，我没有猜测操作。")
        if not secondary_target:
            return fail("target stale", "拖拽终点已经变化，请重新观察。")
        target_element_id = str(secondary_target.get("element_id", ""))
    performed = accessibility_action(
        settings,
        str(original.get("app", "")),
        command,
        str(current_target.get("element_id", "")),
        target_element_id,
        str(action.get("text", "")),
        str(action.get("direction", "down")),
        _safe_int(action.get("amount", 1), 1),
        str(action.get("path", "")),
        int(original.get("window_index", 1)),
    )
    if not performed.get("success"):
        return performed

    deadline = time.monotonic() + (timeout_ms / 1000)
    after: dict[str, Any] = {}
    verification: dict[str, Any] = {"kind": str(expectation.get("kind", "tree_changed")), "satisfied": False}
    while True:
        after = observe_desktop(
            settings,
            str(original.get("app", "")),
            int(original.get("window_index", 1)),
        )
        if not after.get("success"):
            return fail(
                "recovery required: action performed but verification observation failed",
                "动作已经执行，但重新观察失败，需要人工检查结果。",
                {"action_result": performed},
            )
        if not _same_window(before, after):
            return fail(
                "recovery required: verification window changed after action",
                "动作已经执行，但验证时窗口发生变化，需要人工检查结果。",
                {
                    "action_result": performed,
                    "after_observation_id": after.get("observation_id", ""),
                },
            )
        verification = _verify(expectation, before, after, source_target)
        if verification["satisfied"]:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return fail(
                "expectation timeout",
                "动作已经执行，但结果没有满足预期，请人工检查。",
                {
                    "verified": False,
                    "verification": verification,
                    "action_result": performed,
                    "after_observation_id": after.get("observation_id", ""),
                },
            )
        time.sleep(min(0.1, remaining))
    return ok(
        {
            "verified": True,
            "verification": verification,
            "action_result": performed,
            "before_observation_id": before.get("observation_id", ""),
            "after_observation_id": after.get("observation_id", ""),
        },
        "桌面操作已执行并验证成功。",
        "executed and verified desktop step",
    )


def _find_source_target(observation: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
    element_id = str(target.get("element_id", "")).strip()
    candidates = [item for item in observation.get("elements", []) if isinstance(item, dict)]
    if element_id:
        candidates = [item for item in candidates if str(item.get("element_id", "")) == element_id]
    for key in _TARGET_SIGNATURE_KEYS:
        expected = str(target.get(key, "")).strip()
        if expected:
            candidates = [item for item in candidates if str(item.get(key, "")) == expected]
    return candidates[0] if len(candidates) == 1 else None


def _locate_matching_target(
    observation: dict[str, Any], source: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    elements = [item for item in observation.get("elements", []) if isinstance(item, dict)]
    signature = {key: str(source.get(key, "")) for key in _TARGET_SIGNATURE_KEYS if str(source.get(key, ""))}
    semantic = [item for item in elements if all(str(item.get(key, "")) == value for key, value in signature.items())]
    if len(semantic) == 1:
        return semantic[0], "found"
    if len(semantic) > 1:
        return None, "ambiguous"
    element_id = str(source.get("element_id", ""))
    by_id = [item for item in elements if str(item.get("element_id", "")) == element_id]
    if len(by_id) != 1:
        return None, "ambiguous" if len(by_id) > 1 else "missing"
    candidate = by_id[0]
    if signature and not all(str(candidate.get(key, "")) == value for key, value in signature.items()):
        return None, "missing"
    return candidate, "found"


def _verify(
    expectation: dict[str, Any],
    original: dict[str, Any],
    after: dict[str, Any],
    source_target: dict[str, Any],
) -> dict[str, Any]:
    kind = str(expectation.get("kind", "tree_changed")).strip().lower()
    if kind not in _EXPECTATION_KINDS:
        return {"kind": kind, "satisfied": False, "reason": "unsupported expectation"}
    matching, match_state = _locate_matching_target(after, source_target)
    if kind == "element_absent":
        satisfied = match_state == "missing"
    elif kind == "element_present":
        satisfied = match_state == "found"
    elif kind == "element_enabled":
        satisfied = matching is not None and bool(matching.get("enabled"))
    elif kind == "element_disabled":
        satisfied = matching is not None and "enabled" in matching and not bool(matching.get("enabled"))
    else:
        satisfied = after.get("tree_fingerprint") != original.get("tree_fingerprint")
    return {"kind": kind, "satisfied": satisfied}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _preconditions_satisfied(target: dict[str, Any], preconditions: dict[str, Any]) -> bool:
    allowed = {"enabled", "focused", "selected"}
    if set(preconditions) - allowed:
        return False
    return all(key in target and bool(target[key]) is bool(value) for key, value in preconditions.items())


def _same_window(original: dict[str, Any], current: dict[str, Any]) -> bool:
    if str(original.get("process_name", "")) != str(current.get("process_name", "")):
        return False
    first = original.get("window", {})
    second = current.get("window", {})
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    for key in ("window_id", "identifier", "id"):
        expected = str(first.get(key, "")).strip()
        if expected:
            return str(second.get(key, "")).strip() == expected
    expected_title = str(first.get("title", "")).strip()
    if expected_title and str(second.get("title", "")).strip() != expected_title:
        return False
    first_bounds = first.get("bounds")
    second_bounds = second.get("bounds")
    if isinstance(first_bounds, dict) and first_bounds:
        return isinstance(second_bounds, dict) and first_bounds == second_bounds
    return True
