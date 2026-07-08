from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionSpec:
    name: str
    risk: str
    params: dict[str, str]
    description: str
    pending_action_type: str = ""
    pending_param_keys: frozenset[str] = field(default_factory=frozenset)
    pending_required_params: tuple[str, ...] = ()
    pending_title: str = ""

    def catalog_entry(self) -> dict:
        entry = {
            "name": self.name,
            "risk": self.risk,
            "params": self.params,
            "description": self.description,
        }
        if self.pending_action_type:
            entry["pending_action_type"] = self.pending_action_type
        return entry


def api_action_specs() -> tuple[ActionSpec, ...]:
    return _API_ACTION_SPECS


def pending_action_specs() -> tuple[ActionSpec, ...]:
    return _PENDING_ACTION_SPECS


def pending_spec(action_type: str) -> ActionSpec | None:
    return _PENDING_SPECS_BY_TYPE.get(action_type.strip())


def pending_action_types() -> frozenset[str]:
    return frozenset(_PENDING_SPECS_BY_TYPE)


def xcode_params() -> dict[str, str]:
    return {
        "project_path": "string optional",
        "xcode_path": "string optional",
        "scheme": "string optional",
        "configuration": "string optional",
        "destination": "string optional",
        "confirm": "boolean optional",
    }


def _action(
    name: str,
    risk: str,
    params: dict[str, str],
    description: str,
    *,
    pending_action_type: str = "",
    pending_param_keys: frozenset[str] | None = None,
    pending_required_params: tuple[str, ...] = (),
    pending_title: str = "",
) -> ActionSpec:
    return ActionSpec(
        name=name,
        risk=risk,
        params=params,
        description=description,
        pending_action_type=pending_action_type,
        pending_param_keys=pending_param_keys or frozenset(),
        pending_required_params=pending_required_params,
        pending_title=pending_title,
    )


_API_ACTION_SPECS = (
    _action("remember", "low", {"text": "string", "tags": "string optional"}, "Save memory to Obsidian."),
    _action("app_open", "low", {"app_name": "string"}, "Open an allowlisted macOS app."),
    _action("app_focus", "low", {"app_name": "string"}, "Focus an allowlisted macOS app."),
    _action("app_status", "low", {"app_name": "string"}, "Check whether an allowlisted macOS app is running."),
    _action(
        "app_close",
        "medium",
        {"app_name": "string", "confirm": "boolean optional"},
        "Close an app.",
        pending_action_type="app_close",
        pending_param_keys=frozenset({"app_name"}),
        pending_required_params=("app_name",),
    ),
    _action(
        "open_cc_project",
        "low",
        {"project_path": "string optional", "session_id": "string optional"},
        "Open Claude Code/Codex by path.",
    ),
    _action(
        "open_cc_project_named",
        "low",
        {"project": "string", "session_id": "string optional"},
        "Open Claude Code/Codex by project alias.",
    ),
    _action(
        "ask_cc",
        "medium",
        {
            "text": "string",
            "project_path": "string optional",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Send instruction to Claude Code/Codex.",
        pending_action_type="desktop_ask_cc",
        pending_param_keys=frozenset(
            {"text", "project_path", "session_id", "cli", "terminal", "open_if_needed", "allow_frontmost"}
        ),
        pending_required_params=("text",),
    ),
    _action(
        "ask_cc_project",
        "medium",
        {
            "project": "string",
            "text": "string",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Send instruction by project alias.",
        pending_action_type="desktop_ask_cc_project",
        pending_param_keys=frozenset(
            {"project", "text", "session_id", "cli", "terminal", "open_if_needed", "allow_frontmost"}
        ),
        pending_required_params=("project", "text"),
    ),
    _action("check_cc", "low", {"session_id": "string optional"}, "Check Claude Code/Codex status."),
    _action(
        "cc_send_slash_command",
        "medium",
        {
            "command": "string",
            "args": "string optional",
            "session_id": "string optional",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Send a slash command to Claude Code/Codex.",
        pending_action_type="cc_send_slash_command",
        pending_param_keys=frozenset({"command", "args", "session_id", "allow_frontmost"}),
        pending_required_params=("command",),
    ),
    _action(
        "cc_switch_model",
        "medium",
        {
            "model": "string",
            "session_id": "string optional",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Switch Claude Code/Codex model.",
        pending_action_type="cc_switch_model",
        pending_param_keys=frozenset({"model", "session_id", "allow_frontmost"}),
        pending_required_params=("model",),
    ),
    _action(
        "continue_cc",
        "medium",
        {
            "session_id": "string optional",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Send yes/continue.",
        pending_action_type="cc_continue",
        pending_param_keys=frozenset({"session_id", "allow_frontmost"}),
    ),
    _action("focus_cc", "low", {"session_id": "string optional"}, "Focus Claude Code/Codex window."),
    _action(
        "stop_cc",
        "medium",
        {
            "session_id": "string optional",
            "confirm": "boolean optional",
            "allow_frontmost": "boolean optional",
        },
        "Stop Claude Code/Codex session.",
        pending_action_type="cc_stop",
        pending_param_keys=frozenset({"session_id", "allow_frontmost"}),
    ),
    _action("search_obsidian", "low", {"query": "string", "limit": "integer optional"}, "Search Obsidian notes."),
    _action(
        "create_note",
        "low",
        {"note_path": "string", "text": "string optional", "overwrite": "boolean optional"},
        "Create an Obsidian note.",
    ),
    _action("open_note", "low", {"note_path": "string"}, "Open an Obsidian note."),
    _action(
        "append_note",
        "low",
        {"note_path": "string", "text": "string"},
        "Append a note inside Obsidian vault.",
    ),
    _action("append_daily_note", "low", {"text": "string", "date": "YYYY-MM-DD optional"}, "Append daily note."),
    _action("recent_memories", "low", {"limit": "integer optional"}, "Read recent voice memories."),
    _action("health", "low", {}, "Run desktop MCP health checks."),
    _action("config_summary", "low", {}, "Return non-secret config summary."),
    _action("tool_catalog", "low", {}, "Return reader-facing tool catalog."),
    _action("category_registry", "low", {}, "Return desktop category registry."),
    _action(
        "desktop_intent",
        "variable",
        {"category": "string", "intent": "string", "params": "object optional"},
        "Route a generic desktop category intent.",
    ),
    _action("list_projects", "low", {}, "List allowed projects."),
    _action("resolve_project", "low", {"project": "string"}, "Resolve project alias/path."),
    _action("cleanup_sessions", "low", {}, "Clean stale Claude Code/Codex session registrations."),
    _action(
        "xcode_open_project",
        "low",
        {"project_path": "string optional", "xcode_path": "string optional"},
        "Open an allowlisted Xcode project.",
    ),
    _action(
        "xcode_build",
        "medium",
        xcode_params(),
        "Run xcodebuild build.",
        pending_action_type="xcode_build",
        pending_param_keys=frozenset({"project_path", "xcode_path", "scheme", "configuration", "destination"}),
    ),
    _action(
        "xcode_test",
        "medium",
        xcode_params(),
        "Run xcodebuild test.",
        pending_action_type="xcode_test",
        pending_param_keys=frozenset({"project_path", "xcode_path", "scheme", "configuration", "destination"}),
    ),
    _action(
        "xcode_clean",
        "medium",
        xcode_params(),
        "Run xcodebuild clean.",
        pending_action_type="xcode_clean",
        pending_param_keys=frozenset({"project_path", "xcode_path", "scheme", "configuration", "destination"}),
    ),
    _action("xcode_last_errors", "low", {"limit": "integer optional"}, "Return recent xcodebuild errors."),
    _action(
        "browser_open",
        "low",
        {"url": "string", "app_name": "string optional"},
        "Open an http(s) URL in an allowlisted browser.",
    ),
    _action(
        "browser_search",
        "low",
        {"query": "string", "engine": "string optional", "app_name": "string optional"},
        "Search the web in an allowlisted browser.",
    ),
    _action(
        "music_control",
        "low",
        {"command": "play|pause|toggle|next|previous", "app_name": "string optional"},
        "Control an allowlisted music app.",
    ),
    _action(
        "music_search",
        "low",
        {"query": "string", "provider": "apple|netease optional", "browser": "string optional"},
        "Search Apple Music or NetEase Cloud Music in an allowlisted browser.",
    ),
    _action(
        "pending_create",
        "low",
        {"action_type": "string", "params": "object optional"},
        "Create pending action.",
    ),
    _action("pending_list", "low", {"status": "string optional"}, "List pending actions."),
    _action("pending_confirm", "medium", {"action_id": "string"}, "Confirm pending action."),
    _action("pending_cancel", "low", {"action_id": "string"}, "Cancel pending action."),
)

_EXTRA_PENDING_ACTION_SPECS = (
    _action(
        "cc_close_terminal",
        "medium",
        {"terminal": "string optional"},
        "Close the frontmost Terminal/iTerm window.",
        pending_action_type="cc_close_terminal",
        pending_param_keys=frozenset({"terminal"}),
    ),
    _action(
        "cc_send_instruction",
        "medium",
        {"text": "string", "session_id": "string optional", "allow_frontmost": "boolean optional"},
        "Send instruction to a visible Claude Code/Codex session.",
        pending_action_type="cc_send_instruction",
        pending_param_keys=frozenset({"text", "session_id", "allow_frontmost"}),
        pending_required_params=("text",),
    ),
)

_PENDING_ACTION_SPECS = tuple(
    spec for spec in (*_API_ACTION_SPECS, *_EXTRA_PENDING_ACTION_SPECS) if spec.pending_action_type
)

_PENDING_SPECS_BY_TYPE = {spec.pending_action_type: spec for spec in _PENDING_ACTION_SPECS}
