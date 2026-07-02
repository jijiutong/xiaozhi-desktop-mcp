from __future__ import annotations

from xiaozhi_desktop_mcp.api_v1 import actions_catalog, dispatch
from xiaozhi_desktop_mcp.tools.intent import desktop_intent, desktop_intent_catalog


def test_desktop_intent_catalog_includes_core_categories(settings):
    result = desktop_intent_catalog(settings)

    assert result["success"] is True
    assert {"music", "docs", "ai", "dev", "browser", "system"}.issubset(result["categories"])


def test_desktop_intent_docs_create_note(settings):
    result = desktop_intent(
        settings,
        "docs",
        "create",
        {"note_path": "ideas/general-intent", "text": "hello"},
    )

    assert result["success"] is True
    assert result["category"] == "docs"
    assert result["intent"] == "create"
    assert (settings.obsidian_vault / "ideas" / "general-intent.md").read_text(encoding="utf-8") == "hello\n"


def test_desktop_intent_ai_send_creates_pending_action(settings):
    result = desktop_intent(settings, "ai", "send", {"text": "继续修复测试"})

    assert result["success"] is True
    assert result["action"]["action_type"] == "desktop_ask_cc"


def test_api_desktop_intent_dispatch(settings):
    result = dispatch(
        settings,
        "desktop_intent",
        {
            "category": "docs",
            "intent": "create",
            "params": {"note_path": "dispatch/intent", "text": "hello"},
        },
        "req-1",
    )

    assert result["success"] is True
    assert result["action"] == "desktop_intent"


def test_api_actions_catalog_lists_desktop_intent():
    result = actions_catalog()

    names = {action["name"] for action in result["actions"]}
    assert "desktop_intent" in names
    assert "category_registry" in names
