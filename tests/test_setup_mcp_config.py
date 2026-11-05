"""Regression tests for MCP host config name allocation and merge.

Every config here is an isolated fictional file under ``tmp_path``. No real
user config, DCC host, GUI, or MCP client binary is read, started, or written.
Windows/Linux/macOS behaviour is simulated through explicit platform strings
and fake home directories, not by claiming to run on those hosts.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP_SCRIPT = REPO_ROOT / "skills" / "dcc-mcp-blender-setup" / "scripts" / "setup_dcc_mcp_blender.py"
MCP_URL = "http://127.0.0.1:9765/mcp"


@pytest.fixture(scope="module")
def setup_script():
    spec = importlib.util.spec_from_file_location("setup_dcc_mcp_blender_under_test", str(SETUP_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return path.read_text(encoding="utf-8")


def _load_json(path):
    return json.loads(_read(path))


def test_unrelated_same_name_is_not_overwritten_json(tmp_path, setup_script):
    config = tmp_path / "claude_desktop_config.json"
    original = {
        "mcpServers": {
            "blender": {
                "command": "uvx",
                "args": ["blender-mcp"],
                "env": {"BLENDER_PATH": "/opt/blender"},
                "startup_timeout_sec": 30,
                "tool_timeout_sec": 120,
            },
            "filesystem": {"command": "npx", "args": ["-y", "server"]},
        },
        "theme": "dark",
    }
    config.write_text(json.dumps(original, indent=2), encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender-2"
    assert plan["changed"] is True
    assert "blender-2" in plan["dry_run_text"]
    assert "blender-2" in plan["success_text"]

    assert setup_script.apply_mcp_config(plan) == "blender-2"

    merged = _load_json(config)
    assert merged["mcpServers"]["blender"] == original["mcpServers"]["blender"]
    assert merged["mcpServers"]["filesystem"] == original["mcpServers"]["filesystem"]
    assert merged["mcpServers"]["blender-2"] == {"url": MCP_URL}
    assert merged["theme"] == "dark"


def test_existing_product_config_keeps_identity_and_is_idempotent(tmp_path, setup_script):
    config = tmp_path / "claude_desktop_config.json"
    original = {"mcpServers": {"blender": {"url": MCP_URL, "startup_timeout_sec": 45}}}
    original_text = json.dumps(original, indent=2) + "\n"
    config.write_text(original_text, encoding="utf-8")

    first = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert first["chosen_name"] == "blender"
    assert first["is_upgrade"] is True
    assert first["changed"] is False
    assert setup_script.apply_mcp_config(first) == "blender"
    assert _read(config) == original_text

    second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert second["chosen_name"] == "blender"
    assert second["changed"] is False
    assert setup_script.apply_mcp_config(second) == "blender"
    assert _read(config) == original_text


def test_dry_run_does_not_write_and_name_matches_applied(tmp_path, setup_script):
    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    before = _read(config)

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert setup_script.apply_mcp_config(plan, dry_run=True) == plan["chosen_name"]
    assert _read(config) == before
    assert plan["chosen_name"] in plan["dry_run_text"]

    assert setup_script.apply_mcp_config(plan) == plan["chosen_name"]
    assert plan["chosen_name"] in plan["success_text"]
    assert _load_json(config)["mcpServers"]["blender"]["command"] == "uvx"


TOML_FORMS = {
    "standard_table": (
        "[mcp_servers.blender]\n"
        'command = "uvx"\n'
        'args = ["blender-mcp"]\n'
        'env = { BLENDER_PATH = "/opt/blender" }\n'
        "startup_timeout_sec = 30\n"
        "tool_timeout_sec = 120\n"
    ),
    "quoted_key": ('[mcp_servers."blender"]\ncommand = "uvx"\nargs = ["blender-mcp"]\nstartup_timeout_sec = 30\n'),
    "trailing_comment": (
        "[mcp_servers.blender] # existing third-party server\n"
        'command = "uvx"\n'
        'args = ["blender-mcp"]\n'
        "startup_timeout_sec = 30 # keep me\n"
    ),
    "inline_under_parent": (
        "[mcp_servers]\n"
        'blender = { command = "uvx", args = ["blender-mcp"], '
        'env = { BLENDER_PATH = "/opt/blender" }, '
        "startup_timeout_sec = 30, tool_timeout_sec = 120 }\n"
    ),
    "dotted_keys": (
        'mcp_servers.blender.command = "uvx"\n'
        'mcp_servers.blender.args = ["blender-mcp"]\n'
        'mcp_servers.blender.env = { BLENDER_PATH = "/opt/blender" }\n'
        "mcp_servers.blender.startup_timeout_sec = 30\n"
        "mcp_servers.blender.tool_timeout_sec = 120\n"
    ),
    "root_inline": (
        'model = "gpt-5"\n'
        'mcp_servers = { blender = { command = "uvx", args = ["blender-mcp"], '
        "startup_timeout_sec = 30, tool_timeout_sec = 120 } }\n"
    ),
}


@pytest.mark.parametrize("form", sorted(TOML_FORMS))
def test_toml_forms_are_detected_and_preserved(tmp_path, setup_script, form):
    config = tmp_path / (form + ".toml")
    original = TOML_FORMS[form]
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert "blender" in plan["existing_names"], plan
    assert plan["chosen_name"] == "blender-2"
    assert plan["changed"] is True
    assert "blender-2" in plan["dry_run_text"]
    assert "blender-2" in plan["success_text"]

    assert setup_script.apply_mcp_config(plan) == "blender-2"
    merged = _read(config)

    # Every original field and comment survives; the unrelated entry keeps its name.
    for line in original.splitlines():
        if line.strip() and form != "root_inline":
            assert line in merged
    if form == "root_inline":
        assert 'model = "gpt-5"' in merged
        assert "blender = { command" in merged
    assert "blender = { url" not in merged
    assert MCP_URL in merged
    assert "blender-2" in merged

    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(merged)
        assert "blender" in data["mcp_servers"]
        assert data["mcp_servers"]["blender"]["command"] == "uvx"
        assert data["mcp_servers"]["blender-2"]["url"] == MCP_URL


def test_toml_product_entry_keeps_identity_and_is_idempotent(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = '[mcp_servers.blender]\nurl = "%s"\nstartup_timeout_sec = 45\n' % MCP_URL
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender"
    assert plan["is_upgrade"] is True
    assert plan["changed"] is False
    assert setup_script.apply_mcp_config(plan) == "blender"
    assert _read(config) == original

    second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert second["chosen_name"] == "blender"
    assert second["changed"] is False


def test_product_entry_under_custom_name_keeps_that_name(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = '[mcp_servers."my-blender"]\nurl = "%s"\n' % MCP_URL
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "my-blender"
    assert plan["changed"] is False
    assert setup_script.apply_mcp_config(plan) == "my-blender"
    assert _read(config) == original


def test_non_mcp_table_does_not_consume_the_name(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    config.write_text('[profiles.blender]\nmodel = "gpt-5"\n', encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["existing_names"] == []
    assert plan["chosen_name"] == "blender"
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert "[profiles.blender]" in merged
    assert "[mcp_servers.blender]" in merged


def test_strip_toml_comment_keeps_hash_inside_quoted_string(setup_script):
    assert setup_script._strip_toml_comment('url = "http://host/#frag" # tail') == 'url = "http://host/#frag" '
    assert setup_script._strip_toml_comment("[mcp_servers.blender] # mine") == "[mcp_servers.blender] "


def test_inline_table_names_ignore_nested_fields(setup_script):
    body = ' blender = { command = "uvx", env = { A = "B" } }, "quoted-name" = { url = "x" }'
    assert setup_script._inline_table_names(body) == ["blender", "quoted-name"]


def test_free_server_name_skips_multiple_collisions(setup_script):
    assert setup_script.free_server_name("blender", []) == "blender"
    assert setup_script.free_server_name("blender", ["blender"]) == "blender-2"
    assert setup_script.free_server_name("blender", ["blender", "blender-2", "blender-3"]) == "blender-4"


def test_product_marker_is_recognised_without_url_match(setup_script):
    assert setup_script.is_product_entry('command = "dcc-mcp-blender"', "http://other/mcp")
    assert not setup_script.is_product_entry('command = "uvx"', MCP_URL)


def test_malformed_json_raises_without_success(tmp_path, setup_script):
    config = tmp_path / "config.json"
    config.write_text("{ not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        setup_script.plan_mcp_config(config, "blender", MCP_URL)


def test_write_failure_propagates_and_no_file_appears(tmp_path, setup_script):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    config = blocker / "config.json"
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["changed"] is True
    with pytest.raises(OSError):
        setup_script.apply_mcp_config(plan)
    assert not config.exists()


def test_main_dry_run_reports_selected_name_without_writing(tmp_path, setup_script, capsys):
    config = tmp_path / "config.json"
    original = json.dumps({"mcpServers": {"blender": {"command": "uvx"}}})
    config.write_text(original, encoding="utf-8")

    assert setup_script.main(["--dry-run", "--mcp-config", str(config)]) == 0
    assert "blender-2" in capsys.readouterr().out
    assert _read(config) == original


@pytest.mark.parametrize(
    "platform_name,home,env,expected_suffix",
    [
        (
            "win32",
            "C:/Users/tester",
            {"APPDATA": "C:/Users/tester/AppData/Roaming"},
            "AppData/Roaming/Claude/claude_desktop_config.json",
        ),
        (
            "darwin",
            "/Users/tester",
            {},
            "Library/Application Support/Claude/claude_desktop_config.json",
        ),
        (
            "linux",
            "/home/tester",
            {"XDG_CONFIG_HOME": "/home/tester/.config"},
            ".config/Claude/claude_desktop_config.json",
        ),
    ],
)
def test_mcp_config_path_is_platform_resolved(setup_script, platform_name, home, env, expected_suffix):
    assert setup_script.mcp_config_path_for(platform_name, home, env).as_posix().endswith(expected_suffix)


@pytest.mark.parametrize("platform_name", ["win32", "darwin", "linux"])
def test_simulated_client_config_roundtrip(setup_script, tmp_path, platform_name):
    # A mock client: fixed platform string + fake home; no real cross-platform claim.
    home = tmp_path / platform_name
    config = setup_script.mcp_config_path_for(platform_name, str(home), {})
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender-2"
    assert setup_script.apply_mcp_config(plan) == plan["chosen_name"]
    assert setup_script.apply_mcp_config(setup_script.plan_mcp_config(config, "blender", MCP_URL)) == "blender-2"
    data = _load_json(config)
    assert data["mcpServers"]["blender"]["command"] == "uvx"
    assert data["mcpServers"]["blender-2"]["url"] == MCP_URL


# --- Exact-head NACK regressions: valid TOML forms that were mis-detected ---


def test_parent_dotted_subfields_are_detected_and_output_is_valid_toml(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = '[mcp_servers]\nblender.command = "uvx"\nblender.args = ["a"]\n'
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert "blender" in plan["existing_names"], plan
    assert plan["chosen_name"] == "blender-2"
    assert plan["changed"] is True
    assert setup_script.apply_mcp_config(plan) == "blender-2"

    merged = _read(config)
    for line in original.splitlines():
        assert line in merged  # every existing field survives verbatim
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(merged)  # raised TOMLDecodeError before the fix
        assert data["mcp_servers"]["blender"]["command"] == "uvx"
        assert data["mcp_servers"]["blender"]["args"] == ["a"]
        assert data["mcp_servers"]["blender-2"]["url"] == MCP_URL

    second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert second["chosen_name"] == "blender-2"
    assert second["changed"] is False


@pytest.mark.parametrize(
    "original",
    [
        '[mcp_servers]\n"blender".command = "uvx"\n',
        '[mcp_servers]\nblender.env.BLENDER_PATH = "/opt/blender"\n',
        '[mcp_servers]\nblender.command = "uvx"\n"blender".args = ["a"]\n',
    ],
)
def test_parent_dotted_subfield_variants(tmp_path, setup_script, original):
    config = tmp_path / "config.toml"
    config.write_text(original, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert "blender" in plan["existing_names"], plan
    assert plan["chosen_name"] == "blender-2"
    setup_script.apply_mcp_config(plan)
    if sys.version_info >= (3, 11):
        import tomllib

        tomllib.loads(_read(config))  # merged output must stay parseable


def test_scanner_detects_parent_dotted_subfields(setup_script):
    entries = setup_script.scan_toml_mcp_servers('[mcp_servers]\nblender.command = "uvx"\nblender.args = ["a"]\n')
    assert set(entries) == {"blender"}
    assert "command" in entries["blender"]


def test_root_inline_scopes_product_detection_to_each_server(setup_script):
    body = 'mcp_servers = { blender = { command = "uvx" }, core = { url = "%s" } }' % MCP_URL
    entries = setup_script.scan_toml_mcp_servers(body)
    assert set(entries) == {"blender", "core"}
    assert MCP_URL not in entries["blender"]  # sibling URL must not leak
    assert not setup_script.is_product_entry(entries["blender"], MCP_URL)
    assert setup_script.is_product_entry(entries["core"], MCP_URL)


def test_root_inline_multiple_servers_keeps_real_product_entry(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = 'mcp_servers = { blender = { command = "uvx" }, core = { url = "%s" } }\n' % MCP_URL
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "core"
    assert plan["chosen_name"] != "blender"  # unrelated server is not product identity
    assert plan["changed"] is False
    assert setup_script.apply_mcp_config(plan) == "core"
    assert _read(config) == original


def test_root_inline_marker_sibling_does_not_hijack_blender(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = 'mcp_servers = { blender = { command = "uvx" }, note = { command = "dcc-mcp-blender" } }\n'
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "note"
    assert plan["chosen_name"] != "blender"
    assert plan["changed"] is False


def test_root_inline_write_then_rerun_is_idempotent(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    config.write_text('mcp_servers = { blender = { command = "uvx" } }\n', encoding="utf-8")

    first = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert first["chosen_name"] == "blender-2"
    assert first["changed"] is True
    setup_script.apply_mcp_config(first)
    after_first = _read(config)

    second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert second["chosen_name"] == "blender-2"  # unrelated blender must not steal identity
    assert second["changed"] is False
    assert setup_script.apply_mcp_config(second) == "blender-2"
    assert _read(config) == after_first


def test_parent_inline_multi_entry_scopes_product_detection(setup_script):
    original = '[mcp_servers]\nblender = { command = "uvx" }\ncore = { url = "%s" }\n' % MCP_URL
    entries = setup_script.scan_toml_mcp_servers(original)
    assert set(entries) == {"blender", "core"}
    assert MCP_URL not in entries["blender"]
    assert not setup_script.is_product_entry(entries["blender"], MCP_URL)
    assert setup_script.is_product_entry(entries["core"], MCP_URL)


def test_standard_table_multiline_array_is_scoped(setup_script):
    original = '[mcp_servers.blender]\ncommand = "uvx"\nargs = [\n  "a",\n  "b",\n]\nurl = "%s"\n' % MCP_URL
    entries = setup_script.scan_toml_mcp_servers(original)
    assert "blender" in entries
    assert setup_script.is_product_entry(entries["blender"], MCP_URL)


def test_invalid_toml_is_refused_without_writing(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = 'mcp_servers = { blender = { command = "uvx" \n'  # unbalanced
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert _read(config) == original


def test_unknown_suffix_toml_content_is_refused_clearly(tmp_path, setup_script):
    config = tmp_path / "config.conf"
    original = '[mcp_servers]\nblender.command = "uvx"\n'
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert _read(config) == original


def test_python37_fallback_scanner_matches_authoritative_parser(tmp_path, setup_script, monkeypatch):
    # Simulate stock Python 3.7 (no tomllib / no tomli): the scoped stdlib
    # scanner must still produce correct names and idempotent, valid output.
    monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    cases = [
        '[mcp_servers]\nblender.command = "uvx"\nblender.args = ["a"]\n',
        'mcp_servers = { blender = { command = "uvx" }, core = { url = "%s" } }\n' % MCP_URL,
        'mcp_servers = { blender = { command = "uvx" } }\n',
    ]
    for original in cases:
        config = tmp_path / "config.toml"
        config.write_text(original, encoding="utf-8")
        first = setup_script.plan_mcp_config(config, "blender", MCP_URL)
        setup_script.apply_mcp_config(first)
        second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
        assert second["changed"] is False
        if sys.version_info >= (3, 11):
            import tomllib

            tomllib.loads(_read(config))


# --- Independent-NACK regressions: exact URL identity (no raw substring) ---

SIMILAR_URL = "http://127.0.0.1:9765/mcp-other"
LEGACY_URL = "http://legacy.internal:9765/mcp"


def test_exact_url_does_not_hijack_similar_url_json(tmp_path, setup_script):
    config = tmp_path / "config.json"
    original = {
        "mcpServers": {"blender": {"url": SIMILAR_URL, "startup_timeout_sec": 45}},
        "theme": "dark",
    }
    config.write_text(json.dumps(original, indent=2), encoding="utf-8")

    # "mcp" is a substring of "mcp-other": the old raw-text check hijacked it.
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender-2", plan
    assert plan["is_upgrade"] is False
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    merged = _load_json(config)
    assert merged["mcpServers"]["blender"]["url"] == SIMILAR_URL
    assert merged["mcpServers"]["blender"]["startup_timeout_sec"] == 45
    assert merged["mcpServers"]["blender-2"] == {"url": MCP_URL}
    assert merged["theme"] == "dark"


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
def test_exact_url_does_not_hijack_similar_url_toml(tmp_path, setup_script, monkeypatch, no_parser):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[mcp_servers.blender]\nurl = "%s"\nstartup_timeout_sec = 45\n' % SIMILAR_URL
    config.write_text(original, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender-2", plan
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert SIMILAR_URL in merged
    assert MCP_URL in merged
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(merged)
        assert data["mcp_servers"]["blender"]["url"] == SIMILAR_URL
        assert data["mcp_servers"]["blender"]["startup_timeout_sec"] == 45
        assert data["mcp_servers"]["blender-2"]["url"] == MCP_URL


# --- TOML literal strings / triple-quote boundaries ---

# A TOML literal ('...') string ending in a backslash: the backslash is NOT an
# escape, so the closing quote comes right after it. The old scanner skipped the
# backslash-plus-quote pair and mis-scoped the whole inline table.
LITERAL_BACKSLASH_TOML = "mcp_servers = { blender = { command = 'C:\\path\\' } }\n"


def test_string_end_distinguishes_literal_and_basic(setup_script):
    literal = "'C:\\tool\\' tail"
    end = setup_script._string_end(literal, 0)
    assert end is not None
    assert literal[:end] == "'C:\\tool\\'"
    basic = '"a\\"b" tail'
    end = setup_script._string_end(basic, 0)
    assert end is not None
    assert basic[:end] == '"a\\"b"'
    triple = '"""a}b\nc""" tail'
    end = setup_script._string_end(triple, 0)
    assert end is not None
    assert triple[:end] == '"""a}b\nc"""'


def test_balanced_body_ignores_brace_inside_triple_quoted_string(setup_script):
    text = 'mcp_servers = { blender = { note = """a}b""" } }\n'
    span = setup_script._root_inline_span(text)
    assert span is not None
    assert "a}b" in text[span[0] : span[1]]


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
def test_literal_string_trailing_backslash_merges_valid_toml(tmp_path, setup_script, monkeypatch, no_parser):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    config.write_text(LITERAL_BACKSLASH_TOML, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert "blender" in plan["existing_names"], plan
    assert plan["chosen_name"] == "blender-2", plan
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert "blender-2" in merged
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(merged)
        assert data["mcp_servers"]["blender"]["command"] == "C:\\path\\"
        assert data["mcp_servers"]["blender-2"]["url"] == MCP_URL


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
def test_triple_quoted_string_is_refused_on_fallback_and_merged_with_parser(
    tmp_path, setup_script, monkeypatch, no_parser
):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[mcp_servers.blender]\nnote = """line1\nline2"""\n'
    config.write_text(original, encoding="utf-8")

    if no_parser:
        with pytest.raises(ValueError, match="multiline"):
            setup_script.plan_mcp_config(config, "blender", MCP_URL)
        assert _read(config) == original  # no write, no fake success
    else:
        plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
        assert plan["chosen_name"] == "blender-2"
        setup_script.apply_mcp_config(plan)
        if sys.version_info >= (3, 11):
            import tomllib

            data = tomllib.loads(_read(config))
            assert data["mcp_servers"]["blender"]["note"] == "line1\nline2"
            assert data["mcp_servers"]["blender-2"]["url"] == MCP_URL


# --- Python 3.7 fallback: root scope + refusal of unverifiable input ---


def test_root_inline_span_is_root_scoped(setup_script):
    nested = '[profiles.dev]\nmcp_servers = { blender = { command = "uvx" } }\n'
    assert setup_script._root_inline_span(nested) is None
    root = 'mcp_servers = { blender = { command = "uvx" } }\n[other]\nx = 1\n'
    assert setup_script._root_inline_span(root) is not None


def test_fallback_refuses_nested_mcp_servers(tmp_path, setup_script, monkeypatch):
    monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[profiles.dev]\nmcp_servers = { blender = { command = "uvx" } }\n'
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="nested mcp_servers"):
        setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert _read(config) == original


def test_authoritative_nested_mcp_servers_merges_at_root(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    original = '[profiles.dev]\nmcp_servers = { blender = { command = "uvx" } }\n'
    config.write_text(original, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender", plan
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(_read(config))
        assert data["mcp_servers"]["blender"]["url"] == MCP_URL
        assert data["profiles"]["dev"]["mcp_servers"]["blender"]["command"] == "uvx"


def test_fallback_quoted_key_unicode_escape_matches_parser(tmp_path, setup_script, monkeypatch):
    monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[mcp_servers."bl\\u0065nder"]\ncommand = "uvx"\n'
    config.write_text(original, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert "blender" in plan["existing_names"], plan
    assert plan["chosen_name"] == "blender-2", plan


# --- Unicode / DEL TOML encoding ---


def test_toml_quote_escapes_control_chars_and_keeps_unicode(setup_script):
    if sys.version_info < (3, 11):
        pytest.skip("tomllib verification needs Python 3.11+")
    import tomllib

    value = "a🙂\x7fb\x01c\n"
    encoded = setup_script._toml_quote(value)
    assert "\\u007F" in encoded  # DEL must be escaped
    assert "\\u0001" in encoded  # control char escaped
    assert "🙂" in encoded  # non-BMP scalar kept literal
    assert "\\ud83d" not in encoded  # no UTF-16 surrogate pair
    assert tomllib.loads("x = " + encoded)["x"] == value


def test_unicode_and_del_server_name_produces_valid_toml(tmp_path, setup_script):
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5"\n', encoding="utf-8")
    name = "blen🙂der\x7f"
    plan = setup_script.plan_mcp_config(config, name, MCP_URL)
    assert plan["chosen_name"] == name
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert "\x7f" not in merged  # DEL is escaped, never written raw
    if sys.version_info >= (3, 11):
        import tomllib

        assert tomllib.loads(merged)["mcp_servers"][name]["url"] == MCP_URL


# --- JSON/TOML existing product fields are preserved verbatim (no rewrite) ---


def test_json_product_entry_keeps_all_fields_verbatim(tmp_path, setup_script):
    config = tmp_path / "config.json"
    original = {
        "mcpServers": {
            "blender": {
                "url": LEGACY_URL,
                "command": "dcc-mcp-blender",
                "args": ["--serve"],
                "env": {"X": "1"},
                "startup_timeout_sec": 30,
                "tool_timeout_sec": 120,
                "custom": {"keep": True},
            }
        },
        "theme": "dark",
    }
    original_text = json.dumps(original, indent=2)
    config.write_text(original_text, encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["is_upgrade"] is True
    assert plan["chosen_name"] == "blender"
    assert plan["changed"] is False
    assert setup_script.apply_mcp_config(plan) == "blender"
    assert _read(config) == original_text  # no rewrite, no url clobber
    assert _load_json(config)["mcpServers"]["blender"]["url"] == LEGACY_URL
    assert _load_json(config)["mcpServers"]["blender"]["custom"] == {"keep": True}


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
def test_toml_product_entry_keeps_custom_url_verbatim(tmp_path, setup_script, monkeypatch, no_parser):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[mcp_servers.blender]\nurl = "%s"\ncommand = "dcc-mcp-blender"\n' % LEGACY_URL
    config.write_text(original, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["is_upgrade"] is True
    assert plan["changed"] is False
    assert setup_script.apply_mcp_config(plan) == "blender"
    assert _read(config) == original


# --- TOCTOU guard, private staging + atomic replace, symlink, mode ---


def test_apply_refuses_config_changed_since_plan(tmp_path, setup_script):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    config.write_text(json.dumps({"mcpServers": {"other": {}}}), encoding="utf-8")
    changed_text = _read(config)
    with pytest.raises(ValueError, match="changed since the plan"):
        setup_script.apply_mcp_config(plan)
    assert _read(config) == changed_text  # never clobber a newer file


def test_apply_refuses_missing_file_since_plan(tmp_path, setup_script):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    config.unlink()
    with pytest.raises(ValueError, match="changed since the plan"):
        setup_script.apply_mcp_config(plan)
    assert not config.exists()


def test_apply_preserves_file_mode(tmp_path, setup_script, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    before_mode = stat.S_IMODE(config.stat().st_mode)
    recorded = []
    real_chmod = os.chmod

    def spy(path, mode):
        recorded.append(mode)
        return real_chmod(path, mode)

    monkeypatch.setattr(setup_script.os, "chmod", spy)
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    setup_script.apply_mcp_config(plan)
    assert recorded == [before_mode]
    assert stat.S_IMODE(config.stat().st_mode) == before_mode


def test_apply_follows_symlink_and_preserves_link(tmp_path, setup_script):
    real = tmp_path / "real.json"
    real.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real.name)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks unavailable on this host/mode")
    plan = setup_script.plan_mcp_config(link, "blender", MCP_URL)
    setup_script.apply_mcp_config(plan)
    assert link.is_symlink()  # the link itself is not replaced
    assert _load_json(real)["mcpServers"]["blender-2"]["url"] == MCP_URL


def test_apply_leaves_no_private_staging_file(tmp_path, setup_script):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    setup_script.apply_mcp_config(plan)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".mcp-config-")]
    assert leftovers == []


def test_apply_cleans_up_staging_on_replace_failure(tmp_path, setup_script, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(setup_script.os, "replace", failing_replace)
    with pytest.raises(OSError):
        setup_script.apply_mcp_config(plan)
    assert _read(config) == plan["original_text"]  # no fake success, original intact
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".mcp-config-")]
    assert leftovers == []


# --- snippet same-path rejection + non-dry-run main() regression ---


def test_main_rejects_mcp_config_equal_to_generated_snippet(tmp_path, setup_script, monkeypatch):
    monkeypatch.setattr(setup_script, "find_repo_root", lambda: tmp_path)
    snippet = tmp_path / "out" / "mcp-streamable-http.json"
    snippet.parent.mkdir(parents=True, exist_ok=True)
    snippet.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="generated MCP snippet"):
        setup_script.main(["--skip-install", "--mcp-config", str(snippet), "--out-dir", "out"])
    assert _read(snippet) == "{}"


def test_main_non_dry_run_merges_config_and_writes_matching_snippet(tmp_path, setup_script, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mcpServers": {"blender": {"command": "uvx"}}}), encoding="utf-8")
    monkeypatch.setattr(setup_script, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup_script, "resolve_blender_python", lambda _: tmp_path / "fake-python")
    monkeypatch.setattr(setup_script, "install_startup_script", lambda *a, **k: tmp_path / "startup.py")

    assert setup_script.main(["--skip-install", "--mcp-config", str(config), "--out-dir", "out"]) == 0
    assert _load_json(config)["mcpServers"]["blender-2"]["url"] == MCP_URL
    snippet = _load_json(tmp_path / "out" / "mcp-streamable-http.json")
    assert "blender-2" in snippet["mcpServers"]
    assert snippet["mcpServers"]["blender-2"]["url"] == MCP_URL


# --- quoted root mcp_servers key: scanner/builder consistency ---------------
#
# A quoted root key is valid TOML and is already understood by the real parser
# and by scan_toml_mcp_servers (via _parse_key_path). The builder must agree:
# otherwise it appends [mcp_servers.blender-2] beside an existing inline table
# and produces "Cannot declare ... twice" (or writes that invalid file on the
# Python 3.7 fallback). The escaped spelling proves this is not a broadened
# regex but a shared key-path decision.

ROOT_INLINE_KEYS = {
    "bare": "mcp_servers",
    "double_quoted": '"mcp_servers"',
    "single_quoted": "'mcp_servers'",
    "escaped_quoted": '"mcp_serv\\u0065rs"',
}
ROOT_INLINE_KEY_IDS = list(ROOT_INLINE_KEYS)
QUOTED_ROOT_INLINE_TOML = (
    '%s = { blender = { command = "uvx", args = ["--flag"], '
    'startup_timeout_sec = 45 }, filesystem = { command = "npx" } }\n'
)


@pytest.mark.parametrize("key_id", ROOT_INLINE_KEY_IDS, ids=ROOT_INLINE_KEY_IDS)
def test_root_inline_span_uses_key_path_parser_for_quoted_keys(setup_script, key_id):
    text = '%s = { blender = { command = "uvx" } }\n' % ROOT_INLINE_KEYS[key_id]
    span = setup_script._root_inline_span(text)
    assert span is not None
    assert 'command = "uvx"' in text[span[0] : span[1]]


@pytest.mark.parametrize(
    "text",
    [
        '"mcp_servers_extra" = { blender = { command = "uvx" } }\n',
        "'mcp_servers_extra' = { blender = { command = 'uvx' } }\n",
        '"mcp_servers".blender = { command = "uvx" }\n',
        '[profiles.dev]\n"mcp_servers" = { blender = { command = "uvx" } }\n',
        '# "mcp_servers" = { blender = { command = "uvx" } }\n',
    ],
    ids=["double_other", "single_other", "dotted", "nested", "comment"],
)
def test_root_inline_span_ignores_non_root_and_unrelated_keys(setup_script, text):
    assert setup_script._root_inline_span(text) is None


@pytest.mark.parametrize(
    "text",
    [
        'note = "a{b"\n"mcp_servers" = { blender = { command = "uvx" } }\n',
        '# ignored = {\n"mcp_servers" = { blender = { command = "uvx" } }\n',
    ],
    ids=["brace_in_string", "brace_in_comment"],
)
def test_root_inline_open_brace_ignores_strings_and_comments(setup_script, text):
    span = setup_script._root_inline_span(text)
    assert span is not None
    assert 'command = "uvx"' in text[span[0] : span[1]]


def test_root_inline_span_offsets_stay_correct_across_newlines(setup_script):
    text = '"mcp_servers" = {\n  blender = { command = "uvx" },\n}\n'
    span = setup_script._root_inline_span(text)
    assert span is not None
    assert 'command = "uvx"' in text[span[0] : span[1]]


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
@pytest.mark.parametrize("key_id", ROOT_INLINE_KEY_IDS, ids=ROOT_INLINE_KEY_IDS)
def test_quoted_root_inline_key_merges_in_place(tmp_path, setup_script, monkeypatch, no_parser, key_id):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    config.write_text(QUOTED_ROOT_INLINE_TOML % ROOT_INLINE_KEYS[key_id], encoding="utf-8")

    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["existing_names"] == ["blender", "filesystem"], plan
    assert plan["chosen_name"] == "blender-2", plan  # name conflict -> free name
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert "[mcp_servers.blender-2]" not in merged  # inserted inline, never appended
    assert 'command = "uvx"' in merged  # every existing field survives verbatim
    assert 'args = ["--flag"]' in merged
    assert 'filesystem = { command = "npx" }' in merged  # unrelated server kept
    if sys.version_info >= (3, 11):
        import tomllib

        servers = tomllib.loads(merged)["mcp_servers"]  # post-write TOML must be valid
        assert servers["blender"]["command"] == "uvx"
        assert servers["blender"]["args"] == ["--flag"]
        assert servers["blender"]["startup_timeout_sec"] == 45
        assert servers["filesystem"]["command"] == "npx"
        assert servers["blender-2"]["url"] == MCP_URL


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
@pytest.mark.parametrize("key_id", ROOT_INLINE_KEY_IDS, ids=ROOT_INLINE_KEY_IDS)
def test_quoted_root_inline_key_merge_is_idempotent(tmp_path, setup_script, monkeypatch, no_parser, key_id):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    config.write_text(QUOTED_ROOT_INLINE_TOML % ROOT_INLINE_KEYS[key_id], encoding="utf-8")
    first = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    setup_script.apply_mcp_config(first)
    merged = _read(config)

    second = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert second["is_upgrade"] is True, second
    assert second["changed"] is False, second
    assert second["chosen_name"] == "blender-2", second
    assert second["content"] == merged, second
    setup_script.apply_mcp_config(second)
    assert _read(config) == merged


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
@pytest.mark.parametrize("key_id", ROOT_INLINE_KEY_IDS, ids=ROOT_INLINE_KEY_IDS)
def test_quoted_root_inline_key_product_entry_is_no_op(tmp_path, setup_script, monkeypatch, no_parser, key_id):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '%s = { blender = { url = "%s", command = "custom" } }\n' % (
        ROOT_INLINE_KEYS[key_id],
        MCP_URL,
    )
    config.write_text(original, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["is_upgrade"] is True, plan
    assert plan["changed"] is False, plan
    assert plan["chosen_name"] == "blender", plan
    assert setup_script.apply_mcp_config(plan) == "blender"
    assert _read(config) == original  # name and every existing field verbatim
    if sys.version_info >= (3, 11):
        import tomllib

        assert tomllib.loads(original)["mcp_servers"]["blender"]["command"] == "custom"


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
@pytest.mark.parametrize("key", ['"mcp_servers_extra"', "'mcp_servers_extra'"], ids=["double", "single"])
def test_quoted_unrelated_root_key_is_not_treated_as_mcp_servers(tmp_path, setup_script, monkeypatch, no_parser, key):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    config.write_text('%s = { blender = { command = "uvx" } }\n' % key, encoding="utf-8")
    plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert plan["chosen_name"] == "blender", plan
    assert plan["changed"] is True
    setup_script.apply_mcp_config(plan)
    merged = _read(config)
    assert "[mcp_servers.blender]" in merged
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(merged)
        assert data["mcp_servers_extra"]["blender"]["command"] == "uvx"
        assert data["mcp_servers"]["blender"]["url"] == MCP_URL


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
@pytest.mark.parametrize(
    "original",
    [
        '"mcp_servers" = { blender = { command = "uvx" }\n',
        "'mcp_servers' = { blender = { command = \"uvx\" }\n",
    ],
    ids=["double_unbalanced", "single_unbalanced"],
)
def test_invalid_quoted_root_config_is_refused_without_write(tmp_path, setup_script, monkeypatch, no_parser, original):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        setup_script.plan_mcp_config(config, "blender", MCP_URL)
    assert _read(config) == original  # no write, no fake success


@pytest.mark.parametrize("no_parser", [False, True], ids=["tomllib", "py37_fallback"])
def test_nested_quoted_mcp_servers_keeps_root_scope(tmp_path, setup_script, monkeypatch, no_parser):
    if no_parser:
        monkeypatch.setattr(setup_script, "_load_toml_parser", lambda: None)
    config = tmp_path / "config.toml"
    original = '[profiles.dev]\n"mcp_servers" = { blender = { command = "uvx" } }\n'
    config.write_text(original, encoding="utf-8")
    if no_parser:
        with pytest.raises(ValueError, match="nested mcp_servers"):
            setup_script.plan_mcp_config(config, "blender", MCP_URL)
        assert _read(config) == original
    else:
        plan = setup_script.plan_mcp_config(config, "blender", MCP_URL)
        assert plan["chosen_name"] == "blender", plan
        setup_script.apply_mcp_config(plan)
        if sys.version_info >= (3, 11):
            import tomllib

            data = tomllib.loads(_read(config))
            assert data["mcp_servers"]["blender"]["url"] == MCP_URL
            assert data["profiles"]["dev"]["mcp_servers"]["blender"]["command"] == "uvx"


@pytest.mark.skipif(sys.version_info < (3, 8), reason="ast feature_version requires Python 3.8+")
def test_setup_script_and_tests_stay_python37_syntax_compatible():
    ast.parse(_read(SETUP_SCRIPT), filename=str(SETUP_SCRIPT), feature_version=(3, 7))
    ast.parse(_read(Path(__file__)), filename=__file__, feature_version=(3, 7))
