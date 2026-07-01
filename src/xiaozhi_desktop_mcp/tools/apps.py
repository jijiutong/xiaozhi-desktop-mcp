from __future__ import annotations

import subprocess

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_app


def open_app(settings: Settings, app_name: str) -> dict:
    """打开白名单内的 macOS App。"""
    try:
        # App 启动是低风险动作，但仍然限制白名单，防止语音误识别乱开程序。
        app = ensure_allowed_app(app_name, settings.allowed_apps)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里，我没有打开。")

    # 使用 macOS 原生命令 `open -a`，避免自己维护 App 路径。
    completed = subprocess.run(
        ["open", "-a", app],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return fail(
            completed.stderr.strip() or completed.stdout.strip(),
            f"{app} 没有打开成功。",
            {"app": app},
        )
    return ok({"app": app}, f"已打开 {app}。", f"opened {app}")


def close_app(settings: Settings, app_name: str) -> dict:
    """关闭白名单内的 macOS App。"""
    try:
        # 关闭 App 比打开更容易误伤，所以沿用同一套白名单。
        app = ensure_allowed_app(app_name, settings.allowed_apps)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里，我没有关闭。")

    script = (
        f'tell application "{app}"\n'
        "  if it is running then quit\n"
        "end tell"
    )
    completed = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return fail(
            completed.stderr.strip() or completed.stdout.strip(),
            f"{app} 没有关闭成功。",
            {"app": app},
        )
    return ok({"app": app}, f"已关闭 {app}。", f"closed {app}")
