"""Test that all skill directories have the expected structure."""

from __future__ import annotations

import pathlib
import re

import pytest

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
# `metadata:` has to sit at column 0. An indented `metadata:` belongs to
# whichever mapping owns that indent, so it is never the block that
# dcc-mcp-core reads and must not anchor the taxonomy lookup. The trailing
# `(?:#.*)?` keeps the anchor working when the key carries an end-of-line
# comment (`metadata: # taxonomy`): YAML ignores that comment, so the block it
# opens is still the one dcc-mcp-core scores.
_METADATA_RE = re.compile(r"^metadata:[ \t]*(?:#.*)?$", re.MULTILINE)
# Indentation is matched with [ \t] rather than \s so an indent group can never
# swallow the preceding newline, which inflates its length and drops the key.
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


def _indent_width(line: str) -> int:
    """Number of leading spaces/tabs on ``line``."""
    return len(line) - len(line.lstrip(" \t"))


def _strip_comment(line: str) -> str:
    """Return ``line`` without its trailing YAML comment.

    ``#`` only opens a comment at the start of a line or after a space/tab, and
    never inside a quoted scalar, so ``description: "rank #1"`` keeps its ``#``
    while ``dcc-mcp: # taxonomy`` collapses to ``dcc-mcp:``. A comment-only line
    becomes an empty line instead of disappearing: the scanners below key off
    line positions, so dropping lines would shift them.
    """
    quote = ""
    previous = ""
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            # A quote only opens a scalar at the start of a value; a mid-word
            # apostrophe (`blender's`) stays plain text.
            if previous in (" ", "\t"):
                quote = char
        elif char == "#" and (index == 0 or previous in (" ", "\t")):
            return line[:index]
        previous = char
    return line


def _strip_comments(lines: list[str]) -> list[str]:
    """Return ``lines`` with every YAML comment stripped, one entry per input line.

    Idempotent, so a scanner may run it on lines another scanner already cleaned
    without changing the result.
    """
    return [_strip_comment(line) for line in lines]


def _nested_block(lines: list[str], parent_indent: int) -> list[str]:
    """Return the leading run of ``lines`` nested deeper than ``parent_indent``.

    The run stops at the first non-blank line that is not indented deeper than
    the owning key: that line is a sibling or a dedented parent, never a child.

    Comments are stripped first, so a comment-only line — at any indent,
    column 0 included — is blank and cannot end the run. The lines returned
    are stripped too, which is what lets ``_SCALAR_RE`` read a value written as
    ``layer: domain # note``.
    """
    collected = []
    for line in _strip_comments(lines):
        if line.strip() and _indent_width(line) <= parent_indent:
            break
        collected.append(line)
    return collected


def _direct_child_indent(lines: list[str]) -> int:
    """Indent width of the direct children in ``lines``; ``0`` when there are none.

    Every line of a mapping block is indented past its owning key, so a width
    of ``0`` never describes a real child and doubles as "nothing nested here".
    Comments are stripped first: a comment indented shallower than the block is
    not a child and must not define the child indent.
    """
    widths = [_indent_width(line) for line in _strip_comments(lines) if line.strip()]
    return min(widths) if widths else 0


def _find_direct_key(lines: list[str], key: str) -> int:
    """Return the line index of ``key:`` among ``lines``' direct children.

    Returns ``-1`` when the key is absent, and also when it only appears
    indented deeper — a grandchild is not a direct child of the mapping that
    owns ``lines``, and matching it would let a nested decoy stand in for the
    real field.

    Comments are stripped first, so ``dcc-mcp: # taxonomy`` still counts as the
    ``dcc-mcp:`` child.
    """
    child_indent = _direct_child_indent(lines)
    for index, line in enumerate(_strip_comments(lines)):
        if _indent_width(line) == child_indent and line.strip() == key + ":":
            return index
    return -1


def _frontmatter_skill(skill_md: pathlib.Path) -> dict[str, str]:
    """Return the ``metadata.dcc-mcp`` scalar keys declared in a SKILL.md.

    The lookup is anchored twice: first on the top-level ``metadata:`` key,
    then on its **direct** ``dcc-mcp:`` child. A ``dcc-mcp:`` mapping parked
    anywhere else — under a sibling key, or on an indented line inside a folded
    ``description`` scalar — therefore cannot declare ``layer`` / ``stage`` and
    satisfy the taxonomy assertions without those fields existing where
    dcc-mcp-core reads them.

    Deliberately regex/indent based (no PyYAML import) so the assertion runs on
    any interpreter, including the Python 3.7 lane, without a Blender host.
    """
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match, "%s has no YAML front matter" % skill_md

    body = match.group("body")
    metadata_match = _METADATA_RE.search(body)
    assert metadata_match, "%s front matter has no top-level 'metadata' mapping" % skill_md

    metadata_lines = _nested_block(body[metadata_match.end() :].splitlines(), 0)
    dcc_mcp_index = _find_direct_key(metadata_lines, "dcc-mcp")
    assert dcc_mcp_index >= 0, "%s front matter has no 'metadata.dcc-mcp' mapping" % skill_md

    dcc_mcp_lines = _nested_block(metadata_lines[dcc_mcp_index + 1 :], _direct_child_indent(metadata_lines))
    child_indent = _direct_child_indent(dcc_mcp_lines)

    return {
        match_key.group("key"): match_key.group("value")
        for match_key in _SCALAR_RE.finditer("\n".join(dcc_mcp_lines))
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


def test_dcc_mcp_mapping_outside_top_level_metadata_is_ignored(tmp_path):
    """A ``dcc-mcp:`` mapping parked outside ``metadata`` must not be read.

    Combines the two ways a decoy can hide from a naive first-match search:
    under an unrelated top-level key, and under an **indented** ``metadata:``
    that only looks like the real one. Both declare ``layer`` / ``stage`` while
    ``metadata.dcc-mcp`` carries neither, so reading either would let the
    taxonomy tests pass on a SKILL.md dcc-mcp-core cannot score.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: blender-decoy\n"
        'description: "Decoy skill with a dcc-mcp mapping outside the top-level metadata"\n'
        "x-preview:\n"
        "  metadata:\n"
        "    dcc-mcp:\n"
        "      layer: domain\n"
        "      stage: authoring\n"
        "metadata:\n"
        "  dcc-mcp:\n"
        "    dcc: blender\n"
        '    version: "1.0.0"\n'
        "---\n"
        "\n"
        "# blender-decoy\n",
        encoding="utf-8",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["dcc"] == "blender"
    assert "layer" not in fields
    assert "stage" not in fields


def test_indented_dcc_mcp_inside_a_description_scalar_is_ignored(tmp_path):
    """An indented ``dcc-mcp:`` inside a folded ``description`` is prose, not config.

    ``_FRONTMATTER_RE`` is non-greedy, so the description still sits inside the
    front-matter body: an indented ``dcc-mcp:`` written there is text, and only
    appears as a mapping to a line-oriented parser.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: blender-decoy\n"
        "description: >\n"
        "  Mentions a nested mapping in prose:\n"
        "    dcc-mcp:\n"
        "      layer: domain\n"
        "      stage: authoring\n"
        "metadata:\n"
        "  dcc-mcp:\n"
        "    dcc: blender\n"
        '    version: "1.0.0"\n'
        "---\n"
        "\n"
        "# blender-decoy\n",
        encoding="utf-8",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["dcc"] == "blender"
    assert "layer" not in fields
    assert "stage" not in fields


def test_metadata_without_a_dcc_mcp_child_is_rejected(tmp_path):
    """``metadata`` that never declares ``dcc-mcp`` must fail loudly.

    ``dcc-mcp-preview`` is a near-miss key: prefix matching would accept it and
    then report an empty taxonomy instead of a missing one.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: blender-decoy\n"
        'description: "Decoy skill whose metadata has no dcc-mcp child"\n'
        "metadata:\n"
        "  source: bundled\n"
        "  dcc-mcp-preview:\n"
        "    layer: domain\n"
        "    stage: authoring\n"
        "---\n"
        "\n"
        "# blender-decoy\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="metadata.dcc-mcp"):
        _frontmatter_skill(skill_md)


def test_dcc_mcp_nested_below_metadata_is_rejected(tmp_path):
    """``metadata.catalog.dcc-mcp`` is a grandchild, not ``metadata.dcc-mcp``.

    dcc-mcp-core reads the taxonomy at exactly ``metadata.dcc-mcp``, so a
    mapping nested one level deeper is misplaced and must be reported rather
    than silently adopted.
    """
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: blender-decoy\n"
        'description: "Decoy skill with dcc-mcp nested one level too deep"\n'
        "metadata:\n"
        "  catalog:\n"
        "    dcc-mcp:\n"
        "      layer: domain\n"
        "      stage: authoring\n"
        "---\n"
        "\n"
        "# blender-decoy\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="metadata.dcc-mcp"):
        _frontmatter_skill(skill_md)


def _write_front_matter(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """Write a throwaway SKILL.md whose front matter is exactly ``body``."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\n" + body + "---\n\n# blender-comment-fixture\n", encoding="utf-8")
    return skill_md


def test_comment_stripping_keeps_a_hash_inside_a_quoted_scalar():
    """Only a comment-forming ``#`` is stripped; a literal one is kept.

    ``#`` opens a comment at the start of a line or after a space/tab, but never
    inside a quoted scalar and never mid-token, so values such as
    ``"rank #1"`` or a URL fragment survive intact.
    """
    assert _strip_comment("  dcc-mcp: # taxonomy") == "  dcc-mcp: "
    assert _strip_comment("# column 0 comment") == ""
    assert _strip_comment('  note: "rank #1"') == '  note: "rank #1"'
    assert _strip_comment("  url: https://example.com#anchor") == "  url: https://example.com#anchor"


def test_metadata_key_may_carry_an_end_of_line_comment(tmp_path):
    """``metadata: # taxonomy`` must still anchor the taxonomy lookup.

    Regression from PR #217: the anchored parser demanded a bare ``metadata:``
    line, so a trailing comment failed the anchor assertion on a file the
    pre-#217 parser read fine. Comments carry no meaning in YAML, so the anchor
    has to survive one.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture with a commented metadata anchor"\n'
        "metadata: # taxonomy\n"
        "  dcc-mcp:\n"
        "    layer: domain\n"
        "    stage: authoring\n",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["layer"] == "domain"
    assert fields["stage"] == "authoring"


def test_column_zero_comment_between_metadata_and_dcc_mcp_is_skipped(tmp_path):
    """A column 0 comment above ``dcc-mcp:`` must not end the ``metadata:`` block.

    Regression from PR #217: ``_nested_block`` stopped at the first non-blank line
    that is not indented past ``metadata:``, and a full-line comment at column 0
    is exactly such a line, so the ``dcc-mcp:`` child below it was never found.
    The pre-#217 parser searched the whole body and accepted this file.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture with a column 0 comment inside metadata"\n'
        "metadata:\n"
        "# taxonomy lives below\n"
        "  dcc-mcp:\n"
        "    layer: domain\n"
        "    stage: authoring\n",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["layer"] == "domain"
    assert fields["stage"] == "authoring"


def test_dcc_mcp_key_may_carry_an_end_of_line_comment(tmp_path):
    """``dcc-mcp: # taxonomy`` counts as the ``dcc-mcp:`` child.

    Pre-existing limitation, recorded here rather than fixed in PR #217: that
    parser required a bare ``dcc-mcp:`` line and rejected this file outright,
    and the pre-#217 parser did the same for its own ``dcc-mcp:`` search. The
    expected behaviour is acceptance — dcc-mcp-core reads the mapping the same
    way with or without the comment -- and the comment-tolerant scanner now
    delivers it.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture with a commented dcc-mcp key"\n'
        "metadata:\n"
        "  dcc-mcp: # taxonomy\n"
        "    layer: domain\n"
        "    stage: authoring\n",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["layer"] == "domain"
    assert fields["stage"] == "authoring"


def test_layer_value_may_carry_an_end_of_line_comment(tmp_path):
    """``layer: domain # note`` reads as ``domain``, comment excluded.

    Pre-existing limitation, recorded here rather than fixed in PR #217: no
    parser stripped end-of-line comments from scalar lines, so the pre-#217
    parser dropped ``layer`` from this file and the taxonomy tests reported it
    missing. That failure direction is a false FAIL, never a false PASS, but the
    value is unambiguous in YAML, so the scanner now reads it.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture with a commented layer value"\n'
        "metadata:\n"
        "  dcc-mcp:\n"
        "    layer: domain # the layer\n"
        "    stage: authoring\n",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["layer"] == "domain"
    assert fields["stage"] == "authoring"


def test_comment_indented_shallower_than_the_block_is_skipped(tmp_path):
    """A comment indented shallower than its block must not truncate that block.

    Pre-existing limitation, recorded here rather than fixed in PR #217: the
    block run stopped at the first line not indented past ``dcc-mcp:``, so a
    comment at indent 2 inside a four-space block ended the run and dropped
    every scalar below it — ``stage`` here, while ``layer`` still parsed.
    Comments are not structure, so the run now continues past them.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture with a shallow comment inside the block"\n'
        "metadata:\n"
        "  dcc-mcp:\n"
        "    layer: domain\n"
        "  # stage follows\n"
        "    stage: authoring\n",
    )

    fields = _frontmatter_skill(skill_md)

    assert fields["layer"] == "domain"
    assert fields["stage"] == "authoring"


def test_a_commented_out_taxonomy_field_stays_missing(tmp_path):
    """Comment tolerance must never invent a field.

    The failure direction has to stay "false FAIL": a taxonomy that exists only
    inside a comment must keep failing the taxonomy assertions rather than
    silently satisfying them.
    """
    skill_md = _write_front_matter(
        tmp_path,
        "name: blender-comment-fixture\n"
        'description: "Fixture whose taxonomy is commented out"\n'
        "metadata:\n"
        "  dcc-mcp:\n"
        "    dcc: blender\n"
        "    # layer: thin-harness\n"
        "    # stage: authoring\n",
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
