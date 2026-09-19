"""Test that all skill directories have the expected structure."""

from __future__ import annotations

import pathlib
import re

SKILLS_DIR = pathlib.Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"
SKILLS_INDEX = SKILLS_DIR / "SKILLS_INDEX.md"

# Controlled vocabulary for ``metadata.dcc-mcp.layer``.
#
# The values mirror the ``LAYER_*`` constants in dcc-mcp-core
# ``crates/dcc-mcp-skills/src/catalog/scoring.rs``, which multiplies the BM25
# score by a per-layer coefficient. ``domain`` and an unset layer both carry a
# 1.00 multiplier, so backfilling ``layer: domain`` is rank-neutral.
ALLOWED_LAYERS = frozenset({"domain", "infrastructure", "thin-harness", "example"})

# Bundled Blender skills are domain skills except the two infrastructure ones
# (scripting escape hatch and extension installation), which are penalised on
# purpose so typed domain skills win recall. Never ship ``example`` here.
EXPECTED_LAYER_BY_SKILL = {
    "blender-extensions": "infrastructure",
    "blender-scripting": "infrastructure",
}
DEFAULT_LAYER = "domain"

# Controlled vocabulary for ``metadata.dcc-mcp.stage``: the coarse
# progressive-loading phase a skill belongs to. Derived from the SKILLS_INDEX
# "Stage Map" plus the stages already merged into the front matter.
ALLOWED_STAGES = frozenset(
    {
        "bootstrap",
        "scene",
        "authoring",
        "lookdev",
        "animation",
        "simulation",
        "render",
        "interchange",
        "import",
        "pipeline",
        "validation",
        "diagnostics",
    }
)

_FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
_DCC_MCP_TAIL = r"dcc-mcp:"
# Indentation is matched with [ \t] rather than \s so an indent group can never
# swallow the preceding newline, which inflates its length and drops the key.
_DCC_MCP_RE = re.compile(r"^(?P<indent>[ \t]+)" + _DCC_MCP_TAIL + r"[ \t]*$", re.MULTILINE)
_SCALAR_RE = re.compile(
    r"^(?P<indent>[ \t]+)(?P<key>[A-Za-z_][A-Za-z0-9_-]*):[ \t]*(?P<value>\S+)[ \t]*$", re.MULTILINE
)

EXPECTED_SKILLS = [
    "blender-scene",
    "blender-objects",
    "blender-mesh",
    "blender-materials",
    "blender-render",
    "blender-render-farm",
    "blender-scripting",
    "blender-animation",
    "blender-lighting",
    "blender-camera",
    "blender-collection",
    "blender-geometry",
    "blender-shader-nodes",
    "blender-geometry-nodes",
    "blender-physics",
    "blender-import-to-scene",
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


def test_skills_index_mentions_every_bundled_skill():
    """The bundled skill index should stay in sync with skill directories."""
    text = SKILLS_INDEX.read_text(encoding="utf-8")
    indexed = set(re.findall(r"\| `(?P<name>blender-[a-z0-9-]+)` \|", text))
    actual = {path.name for path in SKILLS_DIR.iterdir() if path.is_dir()}

    assert indexed == actual


def _bundled_skill_dirs() -> list[pathlib.Path]:
    """Every bundled skill directory, sorted for stable failure output."""
    return sorted((path for path in SKILLS_DIR.iterdir() if path.is_dir()), key=lambda path: path.name)


def _frontmatter_skill(skill_md: pathlib.Path) -> dict[str, str]:
    """Return the ``metadata.dcc-mcp`` scalar keys declared in a SKILL.md.

    Only scalars nested directly under ``metadata.dcc-mcp`` are returned.
    Matching scalars anywhere in the front matter would let a sibling mapping
    declare ``layer`` / ``stage`` and satisfy the taxonomy assertions without
    those fields existing where dcc-mcp-core reads them.

    Deliberately regex-based (no PyYAML import) so the assertion runs on any
    interpreter, including the Python 3.7 lane, without a Blender host.
    """
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match, "%s has no YAML front matter" % skill_md

    body = match.group("body")
    dcc_match = _DCC_MCP_RE.search(body)
    assert dcc_match, "%s front matter has no 'metadata.dcc-mcp' mapping" % skill_md

    parent_indent = len(dcc_match.group("indent"))
    child_indent = parent_indent + 2

    # Collect the contiguous run of lines nested under `dcc-mcp:` and stop at
    # the first sibling key that is not indented deeper than the mapping.
    block_lines = []
    for line in body[dcc_match.end() :].splitlines():
        if line.strip() and not line.startswith(" " * (parent_indent + 1)):
            break
        block_lines.append(line)
    block = "\n".join(block_lines)

    return {
        match_key.group("key"): match_key.group("value")
        for match_key in _SCALAR_RE.finditer(block)
        if len(match_key.group("indent")) == child_indent
    }


def test_every_skill_declares_layer_and_stage():
    """Every bundled SKILL.md must declare taxonomy ``layer`` and ``stage``."""
    skill_dirs = _bundled_skill_dirs()
    assert skill_dirs, "no bundled skills found under %s" % SKILLS_DIR

    errors = []
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append("%s: missing SKILL.md" % skill_dir.name)
            continue
        fields = _frontmatter_skill(skill_md)
        for field in ("layer", "stage"):
            if not fields.get(field):
                errors.append("%s: missing 'metadata.dcc-mcp.%s'" % (skill_dir.name, field))

    assert not errors, "Skill taxonomy errors:\n" + "\n".join("  - %s" % error for error in errors)


def test_layer_and_stage_use_the_controlled_vocabulary():
    """``layer`` / ``stage`` values must match the agreed taxonomy vocabulary."""
    errors = []
    for skill_dir in _bundled_skill_dirs():
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fields = _frontmatter_skill(skill_md)

        layer = fields.get("layer", "")
        if layer not in ALLOWED_LAYERS:
            errors.append("%s: layer=%r is not one of %s" % (skill_dir.name, layer, ", ".join(sorted(ALLOWED_LAYERS))))

        stage = fields.get("stage", "")
        if stage not in ALLOWED_STAGES:
            errors.append("%s: stage=%r is not one of %s" % (skill_dir.name, stage, ", ".join(sorted(ALLOWED_STAGES))))

    assert not errors, "Skill taxonomy errors:\n" + "\n".join("  - %s" % error for error in errors)


def test_infrastructure_skills_keep_their_ranking_penalty():
    """Only the escape-hatch/install skills may declare a penalised layer.

    ``domain`` scores the same as an unset layer, so backfilling it is safe.
    Marking a domain skill as ``infrastructure`` (0.35) or ``thin-harness``
    (0.20) would silently demote it in skill recall and must stay explicit.
    """
    errors = []
    for skill_dir in _bundled_skill_dirs():
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fields = _frontmatter_skill(skill_md)
        expected = EXPECTED_LAYER_BY_SKILL.get(skill_dir.name, DEFAULT_LAYER)
        actual = fields.get("layer", "")
        if actual != expected:
            errors.append("%s: layer=%r expected %r" % (skill_dir.name, actual, expected))

    assert not errors, "Skill layer errors:\n" + "\n".join("  - %s" % error for error in errors)


def test_taxonomy_fields_must_live_under_metadata_dcc_mcp(tmp_path):
    """A sibling mapping must not satisfy the taxonomy assertions.

    Guards the front-matter parser: matching four-space scalars anywhere in the
    front matter would let an unrelated mapping declare ``layer`` / ``stage``
    and let the taxonomy tests pass on a SKILL.md that never declares them
    under ``metadata.dcc-mcp``.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: blender-decoy\n"
        'description: "Decoy skill with taxonomy declared outside dcc-mcp"\n'
        "metadata:\n"
        "  dcc-mcp:\n"
        "    dcc: blender\n"
        '    version: "1.0.0"\n'
        "  decoy:\n"
        "    layer: domain\n"
        "    stage: authoring\n"
        "---\n"
        "\n"
        "# blender-decoy\n",
        encoding="utf-8",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["dcc"] == "blender"
    assert "layer" not in fields
    assert "stage" not in fields


def test_skills_index_documents_stage_policy_and_task_chains():
    """The index should include the operational guidance requested by issue #28."""
    text = SKILLS_INDEX.read_text(encoding="utf-8")

    for heading in ("## Stage Map", "## Common Task Chains", "## Loading Guidance"):
        assert heading in text

    for required in (
        "Default-load policy",
        "Side-effect profile",
        "Discovery terms",
        "bootstrap",
        "scene",
        "authoring",
        "interchange",
        "pipeline",
        "diagnostics",
        "escape hatch",
    ):
        assert required in text
