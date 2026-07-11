from __future__ import annotations

import argparse
import json
import platform
import sys

from xiaozhi_desktop_mcp.api_v2 import actions_catalog, dispatch
from xiaozhi_desktop_mcp.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Xiaozhi Desktop MCP smoke checks.")
    parser.add_argument("--live", action="store_true", help="Read real browser tabs and music state on macOS.")
    parser.add_argument("--browser", default="chrome")
    parser.add_argument("--music", default="Music")
    args = parser.parse_args()

    settings = load_settings()
    results = []
    catalog = actions_catalog()
    results.append(_check("action_catalog", catalog.get("success") and catalog.get("count", 0) >= 40, catalog))
    config = dispatch(settings, "config_summary", {}, "smoke-config", "mac-smoke")
    results.append(_check("config_summary", config.get("success"), config))
    browser = dispatch(
        settings,
        "browser_capabilities",
        {"app_name": args.browser},
        "smoke-browser-capabilities",
        "mac-smoke",
    )
    results.append(_check("browser_capabilities", browser.get("success"), browser))
    music = dispatch(
        settings,
        "music_capabilities",
        {"app_name": args.music},
        "smoke-music-capabilities",
        "mac-smoke",
    )
    results.append(_check("music_capabilities", music.get("success"), music))

    if args.live:
        if platform.system() != "Darwin":
            results.append(_check("live_platform", False, {"error": "--live requires macOS"}))
        else:
            tabs = dispatch(
                settings,
                "browser_tabs",
                {"app_name": args.browser},
                "smoke-browser-tabs",
                "mac-smoke",
            )
            results.append(_check("browser_tabs", tabs.get("success"), tabs))
            current = dispatch(
                settings,
                "browser_current",
                {"app_name": args.browser},
                "smoke-browser-current",
                "mac-smoke",
            )
            results.append(_check("browser_current", current.get("success"), current))
            status = dispatch(
                settings,
                "music_status",
                {"app_name": args.music},
                "smoke-music-status",
                "mac-smoke",
            )
            results.append(_check("music_status", status.get("success"), status))

    summary = {"success": all(item["success"] for item in results), "checks": results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(item["success"] for item in results) else 1


def _check(name: str, success: object, result: dict) -> dict:
    return {
        "name": name,
        "success": bool(success),
        "error_code": result.get("error_code", ""),
        "error": result.get("error", ""),
    }


if __name__ == "__main__":
    sys.exit(main())
