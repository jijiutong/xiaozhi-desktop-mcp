from __future__ import annotations


def ok(data: dict | None = None, spoken_message: str = "", message: str = "") -> dict:
    """Return a successful tool response with a Xiaozhi-friendly spoken message."""
    result = dict(data or {})
    result["success"] = True
    if message:
        result["message"] = message
    if spoken_message:
        result["spoken_message"] = spoken_message
    return result


def fail(error: str, spoken_message: str = "", data: dict | None = None) -> dict:
    """Return a failed tool response with a Xiaozhi-friendly spoken error."""
    result = dict(data or {})
    result["success"] = False
    result["error"] = error
    result["error_spoken_message"] = spoken_message or _default_error_spoken_message(error)
    return result


def _default_error_spoken_message(error: str) -> str:
    if not error:
        return "操作失败了，但没有返回具体原因。"
    if "allowlisted" in error or "not allowed" in error:
        return "这个操作不在当前白名单里，我没有执行。"
    if "not registered" in error or "not found" in error:
        return "我没有找到对应的会话窗口。"
    if "empty" in error:
        return "内容是空的，我没有执行。"
    if "permission" in error.lower():
        return "权限不够，操作没有成功。"
    return f"操作失败：{error}"
