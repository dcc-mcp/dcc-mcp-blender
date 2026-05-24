"""Validate all SKILL.md front-matter files in the skills directory."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import tools.lint_skills as skill_lint


def test_all_skill_md_files():
    """Every skill directory must have a valid SKILL.md."""
    errors = skill_lint.lint_skills()
    if errors:
        msg = "SKILL.md validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        assert False, msg


def test_tool_metadata_requires_execution_affinity_and_safety_flags(tmp_path, monkeypatch):
    """Local lint must catch fields that the optional external CLI may not enforce yet."""
    skill_dir = tmp_path / "blender-example"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: blender-example
description: "Example Blender skill"
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender]
    search-hint: "example"
    tools: tools.yaml
---

# blender-example
""",
        encoding="utf-8",
    )
    (skill_dir / "tools.yaml").write_text(
        """tools:
  - name: example_tool
    description: "Example"
    source_file: scripts/example_tool.py
""",
        encoding="utf-8",
    )
    (scripts_dir / "example_tool.py").write_text(
        """from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(**kwargs):
    return {"success": True}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_lint, "validate_skill", lambda _path: SimpleNamespace(has_errors=False, issues=[]))

    errors = skill_lint.lint_skills(tmp_path, use_cli=False)

    assert any("missing tool fields" in error and "affinity" in error for error in errors)
    assert any("missing tool fields" in error and "execution" in error for error in errors)
    assert any("missing tool fields" in error and "read_only" in error for error in errors)


def test_tool_metadata_rejects_top_level_bpy_import(tmp_path, monkeypatch):
    """Skill scripts must remain importable without Blender installed."""
    skill_dir = tmp_path / "blender-example"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: blender-example
description: "Example Blender skill"
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender]
    search-hint: "example"
    tools: tools.yaml
---

# blender-example
""",
        encoding="utf-8",
    )
    (skill_dir / "tools.yaml").write_text(
        """tools:
  - name: example_tool
    description: "Example"
    source_file: scripts/example_tool.py
    execution: sync
    affinity: main
    read_only: true
    destructive: false
    idempotent: true
""",
        encoding="utf-8",
    )
    (scripts_dir / "example_tool.py").write_text(
        """import bpy

from dcc_mcp_core.skill import skill_entry


@skill_entry
def main(**kwargs):
    return {"success": True}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_lint, "validate_skill", lambda _path: SimpleNamespace(has_errors=False, issues=[]))

    errors = skill_lint.lint_skills(tmp_path, use_cli=False)

    assert any("host API import must be lazy" in error for error in errors)


if __name__ == "__main__":
    # Allow running as a standalone script
    try:
        test_all_skill_md_files()
        print("All SKILL.md files are valid.")
    except AssertionError as e:
        print(str(e))
        sys.exit(1)
