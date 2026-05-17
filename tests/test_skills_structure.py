"""Test that all skill directories have the expected structure."""

from __future__ import annotations

import pathlib

SKILLS_DIR = pathlib.Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"

EXPECTED_SKILLS = [
    "blender-scene",
    "blender-objects",
    "blender-mesh",
    "blender-materials",
    "blender-render",
    "blender-scripting",
    "blender-animation",
    "blender-lighting",
    "blender-camera",
    "blender-collection",
    "blender-geometry",
]


def test_expected_skills_exist():
    """All expected skill directories should exist."""
    for skill in EXPECTED_SKILLS:
        skill_dir = SKILLS_DIR / skill
        assert skill_dir.is_dir(), f"Missing skill directory: {skill}"


def test_each_skill_has_skill_md():
    """Every skill directory must contain a SKILL.md."""
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists(), f"Missing SKILL.md in {skill_dir.name}"


def test_each_skill_has_scripts_dir():
    """Every skill directory must contain a scripts/ subdirectory."""
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            scripts = skill_dir / "scripts"
            assert scripts.is_dir(), f"Missing scripts/ in {skill_dir.name}"


def test_scripts_have_main_entry():
    """Every script should define a main() function and skill_entry decorator."""
    errors = []
    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        for script in (skill_dir / "scripts").glob("*.py"):
            text = script.read_text(encoding="utf-8")
            if "def main(" not in text:
                errors.append(f"{skill_dir.name}/{script.name}: missing main() function")
            if "skill_entry" not in text:
                errors.append(f"{skill_dir.name}/{script.name}: missing @skill_entry decorator")

    if errors:
        assert False, "Script structure errors:\n" + "\n".join(f"  - {e}" for e in errors)
