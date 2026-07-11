from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..responses import fail, ok
from .apps import applescript_quote

_CONTROL_COMMANDS = frozenset({"focus_tab", "close_tab", "reload", "back", "forward"})


@dataclass(frozen=True)
class BrowserDriver:
    app_name: str
    family: str

    def list_tabs(self) -> dict:
        completed = _run_script(self._tabs_script())
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "读取浏览器标签页失败。")
        tabs = _parse_tabs(completed.stdout)
        return ok(
            {"app": self.app_name, "driver": self.family, "tabs": tabs, "count": len(tabs)},
            f"当前有 {len(tabs)} 个浏览器标签页。",
            "listed browser tabs",
        )

    def current_tab(self) -> dict:
        completed = _run_script(self._current_script())
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "读取当前浏览器页面失败。")
        tabs = _parse_tabs(completed.stdout)
        current = tabs[0] if tabs else None
        return ok(
            {"app": self.app_name, "driver": self.family, "tab": current},
            "已读取当前浏览器页面。" if current else "当前没有浏览器页面。",
            "read current browser tab",
        )

    def _current_script(self) -> str:
        app = applescript_quote(self.app_name)
        if self.family == "safari":
            return f"""
tell application {app}
    if (count of windows) is 0 then return ""
    set currentItem to current tab of front window
    return "1" & tab & index of currentItem & tab & name of currentItem & tab & URL of currentItem
end tell
""".strip()
        return f"""
tell application {app}
    if (count of windows) is 0 then return ""
    set currentIndex to active tab index of front window
    set currentItem to active tab of front window
    return "1" & tab & currentIndex & tab & title of currentItem & tab & URL of currentItem
end tell
""".strip()

    def control(self, command: str, window_index: int = 1, tab_index: int = 1) -> dict:
        normalized = command.strip().lower().replace("-", "_")
        if normalized not in _CONTROL_COMMANDS:
            return fail(f"unsupported browser command: {command}", "这个浏览器控制命令还不支持。")
        if window_index < 1 or tab_index < 1:
            return fail("window_index and tab_index must be positive", "浏览器窗口或标签页编号不正确。")
        completed = _run_script(self._control_script(normalized, window_index, tab_index))
        data = {
            "app": self.app_name,
            "driver": self.family,
            "command": normalized,
            "window_index": window_index,
            "tab_index": tab_index,
        }
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "浏览器操作没有成功。", data)
        return ok(data, "浏览器操作完成。", "browser control completed")

    def capabilities(self) -> list[str]:
        return ["tabs", "current", *_CONTROL_COMMANDS]

    def _tabs_script(self) -> str:
        app = applescript_quote(self.app_name)
        if self.family == "safari":
            return f"""
tell application {app}
    set output to ""
    repeat with w from 1 to count of windows
        repeat with t from 1 to count of tabs of window w
            set output to output & w & tab & t & tab
            set output to output & name of tab t of window w & tab & URL of tab t of window w & linefeed
        end repeat
    end repeat
    return output
end tell
""".strip()
        return f"""
tell application {app}
    set output to ""
    repeat with w from 1 to count of windows
        repeat with t from 1 to count of tabs of window w
            set output to output & w & tab & t & tab
            set output to output & title of tab t of window w & tab & URL of tab t of window w & linefeed
        end repeat
    end repeat
    return output
end tell
""".strip()

    def _control_script(self, command: str, window_index: int, tab_index: int) -> str:
        app = applescript_quote(self.app_name)
        target = f"tab {tab_index} of window {window_index}"
        if self.family == "safari" and command in {"back", "forward"}:
            key = "[" if command == "back" else "]"
            return f"""
tell application {app}
    set current tab of window {window_index} to {target}
    activate
end tell
tell application "System Events" to keystroke {applescript_quote(key)} using command down
""".strip()
        if command == "focus_tab":
            if self.family == "safari":
                statement = f"set current tab of window {window_index} to {target}"
            else:
                statement = f"set active tab index of window {window_index} to {tab_index}"
        elif command == "close_tab":
            statement = f"close {target}"
        elif command == "reload":
            statement = f"set URL of {target} to URL of {target}" if self.family == "safari" else f"reload {target}"
        elif command == "back":
            statement = f"go back {target}"
        else:
            statement = f"go forward {target}"
        return f"tell application {app} to {statement}"


def browser_driver(app_name: str) -> BrowserDriver | None:
    if app_name == "Safari":
        return BrowserDriver(app_name, "safari")
    if app_name in {"Google Chrome", "Microsoft Edge", "Arc"}:
        return BrowserDriver(app_name, "chromium")
    return None


def _run_script(script: str) -> subprocess.CompletedProcess[str]:
    command = ["osascript", "-e", script]
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "browser automation timed out")


def _parse_tabs(output: str) -> list[dict]:
    tabs = []
    for line in output.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        try:
            window_index = int(parts[0])
            tab_index = int(parts[1])
        except ValueError:
            continue
        tabs.append(
            {
                "window_index": window_index,
                "tab_index": tab_index,
                "title": parts[2],
                "url": parts[3],
            }
        )
    return tabs
