"""Validate all SKILL.md front-matter files in the skills directory."""

from __future__ import annotations

import sys

from tools.lint_skills import lint_skills


def test_all_skill_md_files():
    """Every skill directory must have a valid SKILL.md."""
    errors = lint_skills()
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
