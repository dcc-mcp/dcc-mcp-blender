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


@pytest.mark.skipif(sys.version_info < (3, 8), reason="ast feature_version requires Python 3.8+")
def test_setup_script_and_tests_stay_python37_syntax_compatible():
    ast.parse(_read(SETUP_SCRIPT), filename=str(SETUP_SCRIPT), feature_version=(3, 7))
    ast.parse(_read(Path(__file__)), filename=__file__, feature_version=(3, 7))
