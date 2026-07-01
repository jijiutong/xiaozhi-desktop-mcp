from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_inside


_MAX_SEARCH_RESULTS = 10
_MAX_SNIPPET_CHARS = 240
_MAX_RECENT_CHARS = 4000


def save_memory(settings: Settings, text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """把一条语音记忆追加到配置好的 Obsidian 笔记。"""
    content = text.strip()
    if not content:
        return fail("memory text is empty", "要保存的内容是空的，我没有写入 Obsidian。")

    # 只允许写入 Obsidian vault 内的目标文件，避免语音指令写到任意路径。
    target = ensure_inside(
        settings.obsidian_vault,
        settings.obsidian_vault / settings.obsidian_memory_file,
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    # 用时间作为二级标题，后续可以按时间线整理或同步到 RAG/知识库。
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_line = " ".join(f"#{tag.strip()}" for tag in tags.split(",") if tag.strip())
    entry = f"\n## {now}\n\n{content}\n\n{tag_line}\n"

    with target.open("a", encoding="utf-8") as file:
        file.write(entry)

    return ok(
        {"path": str(target)},
        "已记到 Obsidian。",
        "saved memory to Obsidian",
    )


def append_note(settings: Settings, note_path: str, text: str, heading: str = "") -> dict:
    """Append text to a Markdown note inside the configured Obsidian vault."""
    content = text.strip()
    if not content:
        return fail("note text is empty", "要写入的内容是空的，我没有追加。")
    try:
        target = _resolve_note_path(settings, note_path)
    except SafetyError as exc:
        return fail(str(exc), "目标笔记不在 Obsidian 库里，我没有写入。")

    target.parent.mkdir(parents=True, exist_ok=True)
    title = heading.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if title:
        entry = f"\n## {title}\n\n{content}\n"
    else:
        entry = f"\n## {now}\n\n{content}\n"
    with target.open("a", encoding="utf-8") as file:
        file.write(entry)
    return ok(
        {"path": str(target)},
        f"已追加到 {target.name}。",
        "appended note to Obsidian",
    )


def append_daily_note(settings: Settings, text: str, date: str = "", folder: str = "daily") -> dict:
    """Append text to a daily note inside the Obsidian vault."""
    content = text.strip()
    if not content:
        return fail("daily note text is empty", "要写入日记的内容是空的。")
    day = date.strip() or datetime.now().strftime("%Y-%m-%d")
    if not _looks_like_date(day):
        return fail("date must use YYYY-MM-DD", "日期格式需要是 YYYY-MM-DD。")
    folder_name = folder.strip().strip("/") or "daily"
    note_path = f"{folder_name}/{day}.md"
    return append_note(settings, note_path, content, "小智记录")


def search_notes(settings: Settings, query: str, limit: int = 5) -> dict:
    """Search Markdown notes in the Obsidian vault with bounded results."""
    needle = query.strip()
    if not needle:
        return fail("search query is empty", "搜索关键词是空的。")
    max_results = max(1, min(limit, _MAX_SEARCH_RESULTS))
    results: list[dict] = []
    vault = settings.obsidian_vault.expanduser().resolve()
    for path in sorted(vault.rglob("*.md")):
        if _should_skip(path, vault):
            continue
        if path.is_symlink():
            continue
        try:
            safe_path = ensure_inside(vault, path)
            text = safe_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, SafetyError):
            continue
        lower_text = text.lower()
        index = lower_text.find(needle.lower())
        if index < 0:
            continue
        snippet = _snippet(text, index, len(needle))
        results.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(vault)),
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break
    return ok(
        {
            "query": needle,
            "count": len(results),
            "results": results,
        },
        f"在 Obsidian 里找到 {len(results)} 条相关笔记。",
        "searched Obsidian notes",
    )


def recent_memories(settings: Settings, limit: int = 5) -> dict:
    """Return recent memory entries from the configured memory file."""
    try:
        target = ensure_inside(
            settings.obsidian_vault,
            settings.obsidian_vault / settings.obsidian_memory_file,
        )
    except SafetyError as exc:
        return fail(str(exc), "记忆文件不在 Obsidian 库里。")
    if not target.exists():
        return ok(
            {"path": str(target), "count": 0, "memories": []},
            "还没有找到语音记忆。",
            "no recent memories",
        )
    text = target.read_text(encoding="utf-8", errors="ignore")[-_MAX_RECENT_CHARS:]
    entries = _split_memory_entries(text)
    bounded = entries[-max(1, min(limit, 20)) :]
    bounded.reverse()
    return ok(
        {
            "path": str(target),
            "count": len(bounded),
            "memories": bounded,
        },
        f"读取到最近 {len(bounded)} 条语音记忆。",
        "read recent memories",
    )


def _resolve_note_path(settings: Settings, note_path: str) -> Path:
    raw = note_path.strip()
    if not raw:
        raise SafetyError("note path is empty")
    path = Path(raw).expanduser()
    if path.suffix != ".md":
        path = path.with_suffix(".md")
    if not path.is_absolute():
        path = settings.obsidian_vault / path
    return ensure_inside(settings.obsidian_vault, path)


def _looks_like_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _should_skip(path: Path, vault: Path) -> bool:
    try:
        relative = path.relative_to(vault)
    except ValueError:
        return True
    return any(part.startswith(".") for part in relative.parts)


def _snippet(text: str, index: int, needle_len: int) -> str:
    start = max(0, index - _MAX_SNIPPET_CHARS // 2)
    end = min(len(text), index + needle_len + _MAX_SNIPPET_CHARS // 2)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def _split_memory_entries(text: str) -> list[dict]:
    chunks = text.split("\n## ")
    entries = []
    for chunk in chunks:
        clean = chunk.strip()
        if not clean:
            continue
        if "\n" in clean:
            title, body = clean.split("\n", 1)
        else:
            title, body = clean, ""
        entries.append(
            {
                "time": title.strip("# ").strip(),
                "text": body.strip(),
            }
        )
    return entries
