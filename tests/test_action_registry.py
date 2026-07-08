from __future__ import annotations

from xiaozhi_desktop_mcp.action_registry import api_action_specs, pending_action_types
from xiaozhi_desktop_mcp.api_v1 import _ACTION_HANDLERS
from xiaozhi_desktop_mcp.tools.pending_actions import ALLOWED_ACTION_TYPES


def test_api_registry_actions_have_dispatch_handlers():
    registry_actions = {spec.name for spec in api_action_specs()}

    assert registry_actions == set(_ACTION_HANDLERS)


def test_pending_action_types_match_pending_registry():
    assert ALLOWED_ACTION_TYPES == pending_action_types()
