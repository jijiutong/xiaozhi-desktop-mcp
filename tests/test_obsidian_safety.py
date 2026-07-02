from __future__ import annotations

from xiaozhi_desktop_mcp.tools.obsidian import create_note, search_notes


def test_search_notes_skips_symlinks(settings, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (settings.obsidian_vault / "inside.md").write_text("safe needle", encoding="utf-8")
    (outside / "secret.md").write_text("secret needle", encoding="utf-8")
    (settings.obsidian_vault / "linked.md").symlink_to(outside / "secret.md")

    result = search_notes(settings, "needle", 10)

    assert result["success"] is True
    assert [item["relative_path"] for item in result["results"]] == ["inside.md"]


def test_create_note_stays_inside_vault(settings):
    result = create_note(settings, "ideas/today", "hello")

    assert result["success"] is True
    target = settings.obsidian_vault / "ideas" / "today.md"
    assert target.read_text(encoding="utf-8") == "hello\n"
