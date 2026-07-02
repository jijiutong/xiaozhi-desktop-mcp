from __future__ import annotations

from xiaozhi_desktop_mcp.tools.obsidian import search_notes


def test_search_notes_skips_symlinks(settings, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (settings.obsidian_vault / "inside.md").write_text("safe needle", encoding="utf-8")
    (outside / "secret.md").write_text("secret needle", encoding="utf-8")
    (settings.obsidian_vault / "linked.md").symlink_to(outside / "secret.md")

    result = search_notes(settings, "needle", 10)

    assert result["success"] is True
    assert [item["relative_path"] for item in result["results"]] == ["inside.md"]
