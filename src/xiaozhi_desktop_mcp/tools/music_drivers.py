from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..responses import fail, ok
from .apps import applescript_quote

_COMMANDS = frozenset({"play", "pause", "toggle", "play_pause", "next", "previous"})


@dataclass(frozen=True)
class MusicDriver:
    app_name: str
    family: str
    automation_name: str

    def capabilities(self) -> list[str]:
        capabilities = ["toggle", "next", "previous", "status"]
        if self.family == "apple_music":
            capabilities.extend(["play", "pause", "set_volume"])
        if self.family == "netease":
            capabilities.append("search_app")
        return capabilities

    def control(self, command: str) -> dict:
        normalized = command.strip().lower().replace("-", "_") or "toggle"
        if normalized not in _COMMANDS:
            return fail(f"unsupported music command: {command}", "这个音乐控制命令还不支持。")
        if self.family == "netease" and normalized in {"play", "pause"}:
            return fail(
                "NetEase driver cannot guarantee play or pause state; use toggle",
                "网易云音乐无法可靠判断播放状态，请使用播放/暂停切换。",
            )
        script = self._control_script(normalized)
        completed = _run_script(script)
        data = {"app": self.app_name, "driver": self.family, "command": normalized}
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "音乐控制没有成功。", data)
        return ok(data, "音乐操作完成。", "music command completed")

    def status(self) -> dict:
        if self.family != "apple_music":
            return ok(
                {
                    "app": self.app_name,
                    "driver": self.family,
                    "state": "unknown",
                    "track": None,
                    "capabilities": self.capabilities(),
                },
                "网易云音乐已接入控制，当前曲目信息暂不可读。",
                "returned music driver status",
            )
        completed = _run_script(self._apple_status_script())
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "读取音乐状态失败。")
        parts = completed.stdout.strip().split("\t")
        if len(parts) < 5:
            return fail("unexpected Apple Music status response", "音乐状态返回格式不正确。")
        try:
            volume = int(parts[4])
        except ValueError:
            volume = 0
        track = None
        if any(parts[1:4]):
            track = {"name": parts[1], "artist": parts[2], "album": parts[3]}
        return ok(
            {
                "app": self.app_name,
                "driver": self.family,
                "state": parts[0],
                "track": track,
                "volume": volume,
                "capabilities": self.capabilities(),
            },
            "已读取当前音乐状态。",
            "returned music status",
        )

    def set_volume(self, volume: int) -> dict:
        if self.family != "apple_music":
            return fail("exact volume is unavailable for this music driver", "这个音乐 App 暂不支持精确音量控制。")
        safe_volume = min(max(volume, 0), 100)
        completed = _run_script(
            f"tell application {applescript_quote(self.automation_name)} to set sound volume to {safe_volume}"
        )
        if completed.returncode != 0:
            return fail(completed.stderr.strip() or completed.stdout.strip(), "设置音乐音量失败。")
        return ok(
            {"app": self.app_name, "driver": self.family, "volume": safe_volume},
            f"音乐音量已设为 {safe_volume}。",
            "set music volume",
        )

    def search_app(self, query: str) -> dict:
        clean_query = query.strip()
        if not clean_query:
            return fail("music search query is empty", "歌曲或歌手名是空的。")
        if self.family != "netease":
            return fail("in-app search is unavailable for this music driver", "这个音乐 App 暂不支持客户端内搜索。")
        app = applescript_quote(self.automation_name)
        query_value = applescript_quote(clean_query)
        script = f"""
tell application {app} to activate
delay 0.3
tell application "System Events"
    tell process {app}
        keystroke "f" using command down
        delay 0.2
        keystroke {query_value}
        key code 36
    end tell
end tell
""".strip()
        completed = _run_script(script)
        if completed.returncode != 0:
            if _accessibility_denied(completed.stderr):
                return fail(
                    completed.stderr.strip(),
                    "网易云音乐需要辅助功能权限，请在系统设置的隐私与安全性中允许当前终端发送按键。",
                )
            return fail(completed.stderr.strip() or completed.stdout.strip(), "网易云音乐客户端搜索失败。")
        return ok(
            {"app": self.app_name, "driver": self.family, "query": clean_query},
            "已在网易云音乐客户端搜索。",
            "searched music app",
        )

    def _control_script(self, command: str) -> str:
        app = applescript_quote(self.automation_name)
        if self.family == "apple_music":
            apple_command = {
                "play": "play",
                "pause": "pause",
                "toggle": "playpause",
                "play_pause": "playpause",
                "next": "next track",
                "previous": "previous track",
            }[command]
            return f"tell application {app} to {apple_command}"
        key_code, modifier = {
            "play": (49, ""),
            "pause": (49, ""),
            "toggle": (49, ""),
            "play_pause": (49, ""),
            "next": (124, " using command down"),
            "previous": (123, " using command down"),
        }[command]
        return f"""
tell application {app} to activate
tell application "System Events" to tell process {app} to key code {key_code}{modifier}
""".strip()

    def _apple_status_script(self) -> str:
        app = applescript_quote(self.automation_name)
        return f"""
tell application {app}
    set currentState to player state as text
    set currentVolume to sound volume as text
    if currentState is "stopped" then return currentState & tab & "" & tab & "" & tab & "" & tab & currentVolume
    set output to currentState & tab & name of current track & tab
    set output to output & artist of current track & tab & album of current track & tab & currentVolume
    return output
end tell
""".strip()


def music_driver(app_name: str, automation_name: str = "") -> MusicDriver | None:
    target = automation_name or app_name
    if app_name == "Music":
        return MusicDriver(app_name, "apple_music", target)
    if app_name in {"网易云音乐", "NetEase Cloud Music"}:
        return MusicDriver(app_name, "netease", target)
    return None


def _run_script(script: str) -> subprocess.CompletedProcess[str]:
    command = ["osascript", "-e", script]
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "music automation timed out")


def _accessibility_denied(error: str) -> bool:
    normalized = error.lower()
    return "1002" in normalized or "not allowed to send keystrokes" in normalized or "不允许发送按键" in normalized
