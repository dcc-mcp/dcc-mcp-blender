"""Validate all SKILL.md front-matter files in the skills directory."""

from __future__ import annotations

import pathlib
import sys

import yaml
from dcc_mcp_core import validate_skill

SKILLS_DIR = pathlib.Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"

REQUIRED_FIELDS = {"name", "description", "metadata"}
REQUIRED_DCC_MCP_FIELDS = {"dcc", "version", "tags", "search-hint", "tools"}
REQUIRED_TOOL_FIELDS = {"name", "description", "source_file"}


def _parse_front_matter(text: str) -> dict:
    """Extract and parse YAML front-matter delimited by ``---``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    return yaml.safe_load("\n".join(lines[1:end])) or {}


def test_all_skill_md_files():
    """Every skill directory must have a valid SKILL.md."""
    errors = []

    skill_dirs = [d for d in SKILLS_DIR.iterdir() if d.is_dir()]
    assert skill_dirs, f"No skill directories found under {SKILLS_DIR}"

    for skill_dir in sorted(skill_dirs):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: missing SKILL.md")
            continue

        try:
            front = _parse_front_matter(skill_md.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{skill_dir.name}: YAML parse error: {e}")
            continue

        if not front:
            errors.append(f"{skill_dir.name}: empty or missing front-matter")
            continue

        report = validate_skill(str(skill_dir))
        if report.has_errors:
            for issue in report.issues:
                errors.append(f"{skill_dir.name}: {issue.category}: {issue.message}")

        missing = REQUIRED_FIELDS - set(front.keys())
        if missing:
            errors.append(f"{skill_dir.name}: missing fields: {missing}")

        dcc_mcp = front.get("metadata", {}).get("dcc-mcp", {})
        missing_dcc_mcp = REQUIRED_DCC_MCP_FIELDS - set(dcc_mcp.keys())
        if missing_dcc_mcp:
            errors.append(f"{skill_dir.name}: missing metadata.dcc-mcp fields: {missing_dcc_mcp}")
            continue

        tools_file = skill_dir / str(dcc_mcp.get("tools", ""))
        if not tools_file.exists():
            errors.append(f"{skill_dir.name}: tools file not found: {dcc_mcp.get('tools')}")
            continue

        try:
            tools_doc = yaml.safe_load(tools_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            errors.append(f"{skill_dir.name}: tools YAML parse error: {e}")
            continue

        tools = tools_doc.get("tools", [])
        if not isinstance(tools, list) or not tools:
            errors.append(f"{skill_dir.name}: tools file must contain a non-empty 'tools' list")
            continue

        for tool in tools:
            missing_tool = REQUIRED_TOOL_FIELDS - set(tool.keys())
            if missing_tool:
                errors.append(f"{skill_dir.name}/{tool.get('name', '?')}: missing tool fields: {missing_tool}")

            # Verify source file exists
            source = skill_dir / tool.get("source_file", "")
            if not source.exists():
                errors.append(f"{skill_dir.name}: source_file not found: {tool.get('source_file')}")

    if errors:
        msg = "SKILL.md validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        assert False, msg


if __name__ == "__main__":
    # Allow running as a standalone script
    try:
        test_all_skill_md_files()
        print("All SKILL.md files are valid.")
    except AssertionError as e:
        print(str(e))
        sys.exit(1)
