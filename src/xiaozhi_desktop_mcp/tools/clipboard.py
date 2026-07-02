from __future__ import annotations

import subprocess

from ..responses import fail, ok


def clipboard_get() -> dict:
    """Read macOS clipboard text."""
    completed = subprocess.run(["pbpaste"], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return fail(completed.stderr.strip() or completed.stdout.strip(), "剪贴板读取失败。")
    text = completed.stdout
    preview = text[:200]
    return ok({"text": text, "preview": preview, "length": len(text)}, "已读取剪贴板。", "clipboard read")


def clipboard_set(text: str) -> dict:
    """Set macOS clipboard text."""
    if not text:
        return fail("clipboard text is empty", "剪贴板内容是空的，我没有设置。")
    completed = subprocess.run(["pbcopy"], input=text, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return fail(completed.stderr.strip() or completed.stdout.strip(), "剪贴板设置失败。")
    return ok({"length": len(text)}, "已复制到剪贴板。", "clipboard set")
