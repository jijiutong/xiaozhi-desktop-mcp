from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError
from .apps import applescript_quote, resolve_app_name

_SCREENSHOT = "/usr/sbin/screencapture"
_SIPS = "/usr/bin/sips"
_SWIFT = "/usr/bin/swift"
_OCR_SCRIPT = Path(__file__).resolve().parent.parent / "macos_ocr.swift"


def capture_display(display_id: int = 1, max_width: int = 1600) -> dict:
    """Capture one macOS display and return PNG bytes suitable for an LLM client."""
    if display_id < 1 or display_id > 16:
        return fail("display_id must be between 1 and 16", "屏幕编号不正确。")
    if max_width and not 320 <= max_width <= 4096:
        return fail("max_width must be 0 or between 320 and 4096", "截图宽度设置不正确。")

    with tempfile.TemporaryDirectory(prefix="xiaozhi-desktop-capture-") as temp_dir:
        image_path = Path(temp_dir) / "display.png"
        command = [_SCREENSHOT, "-x", "-t", "png", "-D", str(display_id), str(image_path)]
        completed = _run_command(command, 20)
        if completed.returncode != 0 or not image_path.is_file():
            error = completed.stderr.strip() or completed.stdout.strip() or "screen capture failed"
            return fail(error, "截取屏幕失败，请检查屏幕录制权限。")
        resize_error = _resize_image(image_path, max_width)
        if resize_error:
            return fail(resize_error, "缩放截图失败。")
        image_data = image_path.read_bytes()

    return ok(
        {
            "source": "display",
            "display_id": display_id,
            "media_type": "image/png",
            "image_base64": base64.b64encode(image_data).decode("ascii"),
            "byte_count": len(image_data),
            "max_width": max_width,
        },
        "已截取当前屏幕。",
        "captured display",
    )


def capture_window(settings: Settings, app_name: str, window_index: int = 1, max_width: int = 1600) -> dict:
    """Capture a numbered window belonging to an allowlisted app."""
    try:
        app = resolve_app_name(settings, app_name)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里，我没有截图。")
    if window_index < 1 or window_index > 50:
        return fail("window_index must be between 1 and 50", "窗口编号不正确。")
    if max_width and not 320 <= max_width <= 4096:
        return fail("max_width must be 0 or between 320 and 4096", "截图宽度设置不正确。")

    aliases = settings.app_process_aliases.get(app) or settings.app_process_aliases.get(app.lower()) or ()
    process_names = tuple(dict.fromkeys((app, *aliases)))
    process_list = "{" + ", ".join(applescript_quote(name) for name in process_names) + "}"
    script = f"""
tell application "System Events"
    set processNames to name of processes
    repeat with candidate in {process_list}
        if processNames contains (candidate as text) then
            tell process (candidate as text)
                if (count of windows) < {window_index} then error "window not found"
                set targetWindow to window {window_index}
                set {{windowX, windowY}} to position of targetWindow
                set {{windowWidth, windowHeight}} to size of targetWindow
                return windowX & tab & windowY & tab & windowWidth & tab & windowHeight & tab & (candidate as text)
            end tell
        end if
    end repeat
    error "app process not found"
end tell
""".strip()
    bounds_result = _run_command(["/usr/bin/osascript", "-e", script], 15)
    if bounds_result.returncode != 0:
        error = bounds_result.stderr.strip() or bounds_result.stdout.strip() or "window bounds unavailable"
        return fail(error, "读取窗口位置失败，请检查辅助功能权限。", {"app": app})
    try:
        x_text, y_text, width_text, height_text, process_name = bounds_result.stdout.strip().split("\t", 4)
        x, y, width, height = map(int, (x_text, y_text, width_text, height_text))
    except ValueError:
        return fail("invalid window bounds response", "读取到的窗口位置格式不正确。", {"app": app})
    if width < 1 or height < 1:
        return fail("window has invalid bounds", "这个窗口目前不能截图。", {"app": app})

    with tempfile.TemporaryDirectory(prefix="xiaozhi-desktop-capture-") as temp_dir:
        image_path = Path(temp_dir) / "window.png"
        region = f"{x},{y},{width},{height}"
        command = [_SCREENSHOT, "-x", "-t", "png", "-R", region, str(image_path)]
        completed = _run_command(command, 20)
        if completed.returncode != 0 or not image_path.is_file():
            error = completed.stderr.strip() or completed.stdout.strip() or "window capture failed"
            return fail(error, "截取窗口失败，请检查屏幕录制权限。", {"app": app})
        resize_error = _resize_image(image_path, max_width)
        if resize_error:
            return fail(resize_error, "缩放窗口截图失败。", {"app": app})
        image_data = image_path.read_bytes()

    return ok(
        {
            "source": "window",
            "app": app,
            "process_name": process_name,
            "window_index": window_index,
            "bounds": {"x": x, "y": y, "width": width, "height": height},
            "media_type": "image/png",
            "image_base64": base64.b64encode(image_data).decode("ascii"),
            "byte_count": len(image_data),
            "max_width": max_width,
        },
        f"已截取 {app} 的窗口。",
        "captured app window",
    )


def ocr_desktop(
    settings: Settings,
    source: str = "display",
    app_name: str = "",
    window_index: int = 1,
    display_id: int = 1,
    languages: str = "zh-Hans,en-US",
) -> dict:
    """Capture a display or allowlisted app window and recognize text with macOS Vision."""
    normalized_source = source.strip().lower().replace("-", "_")
    if normalized_source == "display":
        captured = capture_display(display_id, 0)
    elif normalized_source == "window":
        captured = capture_window(settings, app_name, window_index, 0)
    else:
        return fail("source must be display or window", "OCR 来源只支持屏幕或窗口。")
    if not captured.get("success"):
        return captured

    try:
        image_data = base64.b64decode(str(captured["image_base64"]), validate=True)
    except (KeyError, ValueError):
        return fail("captured image data is invalid", "截图数据无法识别。")

    with tempfile.TemporaryDirectory(prefix="xiaozhi-desktop-ocr-") as temp_dir:
        image_path = Path(temp_dir) / "input.png"
        image_path.write_bytes(image_data)
        completed = _run_command([_SWIFT, str(_OCR_SCRIPT), str(image_path), languages], 60)
    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip() or "OCR failed"
        return fail(error, "文字识别失败，请确认当前 macOS 支持 Vision OCR。")
    try:
        payload = json.loads(completed.stdout)
        blocks = payload.get("blocks", [])
        text = str(payload.get("text", ""))
        if not isinstance(blocks, list):
            raise ValueError("blocks is not an array")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return fail(f"invalid OCR response: {error}", "文字识别结果格式不正确。")

    return ok(
        {
            "source": normalized_source,
            "app": captured.get("app", ""),
            "display_id": captured.get("display_id", 0),
            "window_index": captured.get("window_index", 0),
            "languages": [item.strip() for item in languages.split(",") if item.strip()],
            "text": text,
            "blocks": blocks,
            "count": len(blocks),
            "bounds_coordinate_system": "vision_normalized_bottom_left",
        },
        f"已识别到 {len(blocks)} 个文本区域。",
        "recognized desktop text",
    )


def _resize_image(image_path: Path, max_width: int) -> str:
    if not max_width:
        return ""
    completed = _run_command([_SIPS, "-Z", str(max_width), str(image_path)], 20)
    if completed.returncode == 0:
        return ""
    return completed.stderr.strip() or completed.stdout.strip() or "image resize failed"


def _run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", f"command timed out after {timeout} seconds")
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))
