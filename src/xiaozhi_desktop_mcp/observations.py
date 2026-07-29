from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from .config import Settings
from .responses import fail, ok
from .storage import ObservationStore
from .tools.accessibility import accessibility_tree

_FINGERPRINT_ELEMENT_KEYS = (
    "element_id",
    "role",
    "subrole",
    "title",
    "description",
    "identifier",
    "enabled",
    "focused",
    "selected",
    "actions",
    "bounds",
)


def observe_desktop(
    settings: Settings,
    app_name: str,
    window_index: int = 1,
    max_depth: int = 5,
    max_elements: int = 200,
) -> dict:
    """Capture a short-lived semantic observation without persisting UI values."""
    observed = accessibility_tree(
        settings,
        app_name,
        window_index=window_index,
        max_depth=max_depth,
        max_elements=max_elements,
        include_values=False,
    )
    if not observed.get("success"):
        return observed

    raw = dict(observed)
    elements = raw.get("elements", [])
    window = raw.get("window", {})
    if not isinstance(elements, list) or not isinstance(window, dict):
        return fail("invalid accessibility observation", "桌面观察结果格式不正确。")

    safe_elements = [_safe_element(item) for item in elements if isinstance(item, dict)]
    identity_strength = "strong" if _window_has_stable_id(window) else "weak"
    payload = {
        "app": str(raw.get("app", "")),
        "process_name": str(raw.get("process_name", "")),
        "window_index": window_index,
        "window": _without_values(window),
        "identity_strength": identity_strength,
        "tree_fingerprint": _tree_fingerprint(window, safe_elements),
        "elements": safe_elements,
        "count": len(safe_elements),
        "truncated": bool(raw.get("truncated")),
    }
    observation_id = f"obs_{uuid4().hex[:16]}"
    record = ObservationStore(settings).create(observation_id, payload)
    return ok(record, f"已观察 {record['app']} 的当前界面。", "created desktop observation")


def _safe_element(element: dict[str, Any]) -> dict[str, Any]:
    return {key: _without_values(element[key]) for key in _FINGERPRINT_ELEMENT_KEYS if key in element}


def _without_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_values(item) for key, item in value.items() if key.lower() != "value"}
    if isinstance(value, list):
        return [_without_values(item) for item in value]
    return value


def _window_has_stable_id(window: dict[str, Any]) -> bool:
    return any(str(window.get(key, "")).strip() for key in ("window_id", "identifier", "id"))


def _tree_fingerprint(window: dict[str, Any], elements: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        {"window": _without_values(window), "elements": elements},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
