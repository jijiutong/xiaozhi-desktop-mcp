from __future__ import annotations

import re
from datetime import datetime

from ..config import Settings
from ..responses import fail, ok
from ..safety import ensure_inside


def _slugify_title(title: str) -> str:
    """把任务标题变成适合文件名的短 slug，保留中文和英文数字。"""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", title.strip()).strip("-")
    return slug[:60] or "cc-task"


def _yaml_string(value: str) -> str:
    """把字符串包成简单 YAML 安全写法，避免冒号和引号破坏 frontmatter。"""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def create_task(
    settings: Settings,
    title: str,
    instruction: str,
    project_path: str = "",
    priority: str = "normal",
) -> dict:
    """创建 cc/Codex Markdown 待办任务，但不执行任何命令。"""
    clean_title = title.strip()
    clean_instruction = instruction.strip()
    if not clean_title:
        return fail("task title is empty", "任务标题是空的，我没有创建。")
    if not clean_instruction:
        return fail("task instruction is empty", "任务内容是空的，我没有创建。")

    created_at = datetime.now()
    task_dir = settings.cc_tasks_dir.expanduser().resolve()
    task_dir.mkdir(parents=True, exist_ok=True)

    # 文件名带时间戳，避免同名任务覆盖；标题 slug 方便人眼扫描。
    filename = f"{created_at.strftime('%Y%m%d-%H%M%S')}-{_slugify_title(clean_title)}.md"
    target = ensure_inside(task_dir, task_dir / filename)

    effective_project_path = project_path.strip() or settings.default_project_root
    clean_priority = priority.strip() or "normal"

    # 任务文件是“待确认动作”，不是执行入口。后续可以由人工或确认工具消费。
    body = f"""---
title: {_yaml_string(clean_title)}
status: pending
priority: {_yaml_string(clean_priority)}
created: {_yaml_string(created_at.strftime('%Y-%m-%d %H:%M:%S'))}
project_path: {_yaml_string(effective_project_path)}
source: xiaozhi-desktop-mcp
---

# {clean_title}

## Instruction

{clean_instruction}

## Execution Note

This file is a pending task for Claude Code/Codex. It was created by voice via
Xiaozhi, but no command has been executed automatically.

Suggested next step: review the task, confirm the project path, then run the
coding agent manually or through a future confirmation tool.
"""

    with target.open("w", encoding="utf-8") as file:
        file.write(body)

    return ok(
        {
            "path": str(target),
            "status": "pending",
        },
        f"已创建待办任务：{clean_title}。我还没有执行任何命令。",
        "created cc task without executing commands",
    )
