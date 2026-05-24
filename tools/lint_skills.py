"""Validate bundled Blender skills against the current dcc-mcp-core contract."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import List, Optional

import yaml
from dcc_mcp_core import validate_skill

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_DIR = ROOT / "src" / "dcc_mcp_blender" / "skills"

REQUIRED_FIELDS = {"name", "description", "metadata"}
REQUIRED_DCC_MCP_FIELDS = {"dcc", "version", "tags", "search-hint", "tools"}
REQUIRED_TOOL_FIELDS = {
    "name",
    "description",
    "source_file",
    "execution",
    "affinity",
    "read_only",
    "destructive",
    "idempotent",
}
VALID_EXECUTION = {"sync", "async"}
VALID_AFFINITY = {"main", "any"}
SAFETY_FIELDS = {"read_only", "destructive", "idempotent"}


def _find_dcc_mcp_cli() -> Optional[str]:
    exe = shutil.which("dcc-mcp-cli")
    if exe:
        return exe
    if sys.platform == "win32":
        local_appdata = pathlib.Path.home() / "AppData" / "Local"
        candidate = local_appdata / "dcc-mcp" / "bin" / "dcc-mcp-cli.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def lint_skills_with_cli(skills_dir: pathlib.Path, warnings_as_errors: bool = False) -> Optional[List[str]]:
    """Run the standalone dcc-mcp-cli skill linter when it is installed."""
    cli = _find_dcc_mcp_cli()
    if cli is None:
        return None

    cmd = [cli, "lint"]
    if warnings_as_errors:
        cmd.append("--warnings-as-errors")
    cmd.append(str(skills_dir))
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, capture_output=True, text=True)
    output = (proc.stdout or proc.stderr).strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        return [output or f"dcc-mcp-cli lint failed with exit code {proc.returncode}"] if proc.returncode else []

    errors: List[str] = []
    for report in payload.get("reports", []):
        for issue in report.get("issues", []):
            severity = issue.get("severity", "unknown")
            if severity == "error" or warnings_as_errors:
                errors.append(f"{report.get('skill_dir')}: {issue.get('category')}: {issue.get('message')}")

    if proc.returncode != 0 and not errors:
        errors.append(output or f"dcc-mcp-cli lint failed with exit code {proc.returncode}")
    return errors


def _parse_front_matter(text: str) -> dict:
    """Extract and parse YAML front matter delimited by ``---``."""
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


def lint_skills(
    skills_dir: pathlib.Path = DEFAULT_SKILLS_DIR,
    *,
    use_cli: bool = True,
    warnings_as_errors: bool = False,
) -> List[str]:
    """Return validation errors for all skill directories under *skills_dir*."""
    errors: List[str] = []
    if use_cli:
        cli_errors = lint_skills_with_cli(skills_dir, warnings_as_errors=warnings_as_errors)
        if cli_errors is not None:
            errors.extend(cli_errors)

    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    if not skill_dirs:
        return [f"No skill directories found under {skills_dir}"]

    for skill_dir in sorted(skill_dirs):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: missing SKILL.md")
            continue

        try:
            front = _parse_front_matter(skill_md.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{skill_dir.name}: YAML parse error: {exc}")
            continue

        if not front:
            errors.append(f"{skill_dir.name}: empty or missing front matter")
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
        except yaml.YAMLError as exc:
            errors.append(f"{skill_dir.name}: tools YAML parse error: {exc}")
            continue

        tools = tools_doc.get("tools", [])
        if not isinstance(tools, list) or not tools:
            errors.append(f"{skill_dir.name}: tools file must contain a non-empty 'tools' list")
            continue

        for tool in tools:
            tool_name = tool.get("name", "?")
            missing_tool = REQUIRED_TOOL_FIELDS - set(tool.keys())
            if missing_tool:
                errors.append(f"{skill_dir.name}/{tool_name}: missing tool fields: {missing_tool}")

            execution = tool.get("execution")
            if execution is not None and execution not in VALID_EXECUTION:
                errors.append(
                    f"{skill_dir.name}/{tool_name}: invalid execution {execution!r}; "
                    f"expected one of {sorted(VALID_EXECUTION)}"
                )

            affinity = tool.get("affinity")
            if affinity is not None and affinity not in VALID_AFFINITY:
                errors.append(
                    f"{skill_dir.name}/{tool_name}: invalid affinity {affinity!r}; "
                    f"expected one of {sorted(VALID_AFFINITY)}"
                )

            for field in SAFETY_FIELDS:
                if field in tool and not isinstance(tool[field], bool):
                    errors.append(f"{skill_dir.name}/{tool_name}: {field} must be a boolean")

            if execution == "async" and "timeout_hint_secs" not in tool:
                errors.append(f"{skill_dir.name}/{tool_name}: async tools must declare timeout_hint_secs")

            source_file = tool.get("source_file", "")
            if source_file and pathlib.PurePosixPath(source_file).parts[:1] != ("scripts",):
                errors.append(f"{skill_dir.name}/{tool_name}: source_file must be under scripts/: {source_file}")

            source = skill_dir / source_file
            if not source.exists():
                errors.append(f"{skill_dir.name}: source_file not found: {source_file}")
                continue

            try:
                script_text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"{skill_dir.name}/{tool_name}: could not read source file as UTF-8: {exc}")
                continue

            for forbidden in ("import bpy", "from bpy"):
                if any(line.startswith(forbidden) for line in script_text.splitlines()):
                    errors.append(
                        f"{skill_dir.name}/{tool_name}: host API import must be lazy inside the tool function"
                    )

    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-dir", type=pathlib.Path, default=DEFAULT_SKILLS_DIR)
    parser.add_argument("--no-cli", action="store_true", help="Use the Python validator even when dcc-mcp-cli exists.")
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args(argv)

    errors = lint_skills(
        args.skills_dir,
        use_cli=not args.no_cli,
        warnings_as_errors=args.warnings_as_errors,
    )
    if errors:
        print("SKILL.md validation errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("All SKILL.md files are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
