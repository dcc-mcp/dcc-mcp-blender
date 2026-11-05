"""Prepare a Blender bundled-Python environment for dcc-mcp-blender MCP use."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_MCP_URL = "http://127.0.0.1:9765/mcp"
STARTUP_SCRIPT_NAME = "dcc_mcp_blender_startup.py"
STARTUP_SCRIPT = '''"""Auto-start dcc-mcp-blender from Blender's startup registry."""

from __future__ import annotations

_server = None
_owns_server = False


def register():
    """Start the MCP server once Blender has loaded this startup script."""
    global _owns_server, _server
    if _server is not None and getattr(_server, "is_running", True):
        return _server

    from dcc_mcp_core import capture_bootstrap_errors

    with capture_bootstrap_errors(
        "blender",
        min_core_version="0.20.0",
        phase="startup",
    ):
        from dcc_mcp_blender import get_server, start_server

        existing = get_server()
        if existing is not None and getattr(existing, "is_running", False):
            _server = existing
            _owns_server = False
            return _server

        _server = start_server()
        _owns_server = True
        return _server


def unregister():
    """Stop the server started by this startup script."""
    global _owns_server, _server
    if _server is None:
        return

    try:
        if not _owns_server:
            return

        from dcc_mcp_blender import get_server, stop_server

        if get_server() is _server:
            stop_server()
    finally:
        _server = None
        _owns_server = False
'''


def run(command: list[str], cwd: Optional[Path] = None) -> None:
    print("+ " + " ".join(command))
    subprocess.check_call(command, cwd=str(cwd) if cwd else None)


def _glob_blender_python(root: str) -> Iterable[Path]:
    """Yield Blender bundled interpreters under *root* (``<ver>/python/bin/python*``)."""
    if not root:
        return
    exe = "python.exe" if os.name == "nt" else "python*"
    # Blender layouts:
    #   Windows: <root>/Blender X.Y/X.Y/python/bin/python.exe
    #   Linux:   <root>/blender-X.Y.Z/X.Y/python/bin/python3.X
    #   macOS:   <root>/Blender.app/Contents/Resources/X.Y/python/bin/python3.X
    patterns = [
        os.path.join(root, "*", "*", "python", "bin", exe),
        os.path.join(root, "*", "python", "bin", exe),
        os.path.join(root, "*", "Contents", "Resources", "*", "python", "bin", exe),
        os.path.join(root, "Contents", "Resources", "*", "python", "bin", exe),
        os.path.join(root, "*", "*", "Contents", "Resources", "*", "python", "bin", exe),
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    # Prefer the newest Blender version (lexical sort is good enough for X.Y dirs).
    for match in sorted(matches, reverse=True):
        yield Path(match)


def candidate_blender_python_paths() -> Iterable[Path]:
    env_value = os.environ.get("BLENDER_PYTHON") or os.environ.get("DCC_MCP_BLENDER_PYTHON")
    if env_value:
        yield Path(env_value)

    # If a `blender` launcher is on PATH, its bundled python sits next to it
    # under <install>/<major.minor>/python/bin/python(.exe).
    blender_launcher = shutil.which("blender")
    if blender_launcher:
        install_root = Path(blender_launcher).resolve().parent
        for found in _glob_blender_python(str(install_root)):
            yield found

    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
        ]
        for root in roots:
            if not root:
                continue
            yield from _glob_blender_python(os.path.join(root, "Blender Foundation"))
    elif sys.platform == "darwin":
        yield from _glob_blender_python("/Applications")
        yield from _glob_blender_python(os.path.expanduser("~/Applications"))
    else:
        yield from _glob_blender_python("/usr/share/blender")
        yield from _glob_blender_python("/opt/blender")
        yield from _glob_blender_python(os.path.expanduser("~/blender"))
        snap = shutil.which("blender")
        if snap:
            yield from _glob_blender_python("/snap/blender/current")


def resolve_blender_python(explicit: Optional[str]) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return path
        raise SystemExit("Blender Python does not exist: %s" % path)

    seen = set()
    for path in candidate_blender_python_paths():
        expanded = path.expanduser()
        key = str(expanded).lower()
        if key in seen:
            continue
        seen.add(key)
        if expanded.exists():
            return expanded

    raise SystemExit(
        "Could not find Blender's bundled Python. Re-run with --blender-python "
        '(e.g. "C:\\Program Files\\Blender Foundation\\Blender 4.5\\4.5\\python\\bin\\python.exe"), '
        "or set BLENDER_PYTHON to the full path."
    )


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists() and (parent / "src" / "dcc_mcp_blender").exists():
            return parent
    return Path.cwd()


def install_package(
    blender_python: Path,
    source: str,
    repo_root: Path,
    skip_install: bool,
    user_install: bool = False,
) -> None:
    if skip_install:
        print("Skipping pip install because --skip-install was passed.")
        return

    ensurepip_command = [str(blender_python), "-m", "ensurepip", "--upgrade"]
    pip_upgrade_command = [str(blender_python), "-m", "pip", "install", "--upgrade", "pip"]
    if user_install:
        ensurepip_command.append("--user")
        pip_upgrade_command.append("--user")
    run(ensurepip_command)
    run(pip_upgrade_command)

    # dcc-mcp-blender ships no optional install extras (no `[sidecar]`); install
    # the package plainly. The dcc-mcp-core dependency is resolved transitively.
    install_command = [str(blender_python), "-m", "pip", "install"]
    if user_install:
        install_command.append("--user")
    if source == "local":
        run(install_command + ["-e", "."], cwd=repo_root)
    elif source == "pypi":
        run(install_command + ["--upgrade", "dcc-mcp-blender"])
    else:
        raise SystemExit("Unknown source: %s" % source)


def _blender_version_from_python(blender_python: Path) -> str:
    """Return ``major.minor`` from Blender's ``<version>/python/bin`` layout."""
    version = blender_python.parent.parent.parent.name
    if not version or not version[0].isdigit():
        raise SystemExit("Could not infer Blender version from %s; pass --startup-scripts-dir." % blender_python)
    return version


def resolve_blender_scripts_dir(blender_python: Path, explicit: Optional[str]) -> Path:
    """Resolve Blender's writable per-user scripts directory."""
    if explicit:
        return Path(explicit).expanduser()

    configured = os.environ.get("BLENDER_USER_SCRIPTS")
    if configured:
        return Path(configured).expanduser()

    version = _blender_version_from_python(blender_python)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise SystemExit("APPDATA is unavailable; pass --startup-scripts-dir.")
        return Path(appdata) / "Blender Foundation" / "Blender" / version / "scripts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Blender" / version / "scripts"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "blender" / version / "scripts"


def install_startup_script(blender_python: Path, explicit_scripts_dir: Optional[str] = None) -> Path:
    """Install the Blender 5.x-registerable bridge into the user startup directory."""
    startup_dir = resolve_blender_scripts_dir(blender_python, explicit_scripts_dir) / "startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    startup_path = startup_dir / STARTUP_SCRIPT_NAME
    startup_path.write_text(STARTUP_SCRIPT, encoding="utf-8")
    print("Wrote %s" % startup_path)
    return startup_path


def blender_launch_command(executable: str, user_install: bool = False) -> list[str]:
    """Return the launch command required for the selected pip install scope."""
    command = [executable]
    if user_install:
        command.append("--python-use-system-env")
    return command


def verify_import(blender_python: Path) -> None:
    code = (
        "import dcc_mcp_blender; "
        "print('dcc-mcp-blender', dcc_mcp_blender.__version__); "
        "import dcc_mcp_core; "
        "print('dcc-mcp-core import ok')"
    )
    run([str(blender_python), "-c", code])


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Wrote %s" % path)


# --- MCP host config merge -------------------------------------------------
#
# Operators may point this script at an existing MCP host config instead of
# pasting the generated snippet. Never replace that file: an unrelated server
# already using the requested name keeps its own entry, every existing field
# (``command`` / ``args`` / ``env`` / ``startup_timeout_sec`` /
# ``tool_timeout_sec`` ...) survives verbatim, and a product entry that is
# already configured keeps its name and makes repeated runs a no-op.
#
# The scanner is deliberately regex based (no tomllib): it works on Python
# 3.7+ and covers standard tables, quoted keys, inline tables, dotted keys,
# root-level inline tables and trailing comments in one code path.

PRODUCT_MARKERS = ("dcc-mcp-blender", "dcc_mcp_blender")

_KEY_PATTERN = r"""(?:"([^"]+)"|'([^']+)'|([A-Za-z0-9_-]+))"""
_TOML_CHILD_HEADER = re.compile(r"^\s*\[\s*mcp_servers\s*\.\s*" + _KEY_PATTERN + r"\s*\]\s*$")
_TOML_PARENT_HEADER = re.compile(r"^\s*\[\s*mcp_servers\s*\]\s*$")
_TOML_ANY_HEADER = re.compile(r"^\s*\[")
_TOML_INLINE_ENTRY = re.compile(r"^\s*" + _KEY_PATTERN + r"\s*=\s*\{")
_TOML_DOTTED_KEY = re.compile(r"^\s*mcp_servers\s*\.\s*" + _KEY_PATTERN + r"\s*[.=]")
_TOML_ROOT_INLINE = re.compile(r"(?m)^\s*mcp_servers\s*=\s*\{")


def _key_from_match(match: Any) -> str:
    """Return the captured TOML key (quoted or bare) from a regex match."""
    return match.group(1) or match.group(2) or match.group(3)


def _strip_toml_comment(line: str) -> str:
    """Remove a trailing ``#`` comment while honouring quoted strings."""
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _balanced_body(text: str, open_index: int) -> Optional[str]:
    """Return the body of the inline table opened at *open_index*."""
    depth = 0
    quote = ""
    index = open_index
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in ('"', "'"):
            quote = char
        elif char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
        index += 1
    return None


def _root_inline_span(text: str) -> Optional[Tuple[int, int]]:
    """Return ``(body_start, body_end)`` for a root ``mcp_servers = {...}``."""
    match = _TOML_ROOT_INLINE.search(text)
    if not match:
        return None
    open_index = text.index("{", match.start())
    body = _balanced_body(text, open_index)
    if body is None:
        return None
    return open_index + 1, open_index + 1 + len(body)


def _inline_table_names(body: str) -> List[str]:
    """Return top-level keys of a TOML inline-table body.

    Nested ``{...}`` values are skipped so fields such as ``command`` are not
    mistaken for MCP server names.
    """
    names: List[str] = []
    key_assignment = re.compile(_KEY_PATTERN + r"\s*=")
    index = 0
    depth = 0
    while index < len(body):
        # Try a key assignment before treating a quote as a string value, so
        # quoted keys such as "my-server" are recognised as top-level names.
        if depth == 0:
            match = key_assignment.match(body, index)
            if match:
                names.append(_key_from_match(match))
                index = match.end()
                continue
        char = body[index]
        if char in ('"', "'"):
            quote = char
            index += 1
            while index < len(body):
                if body[index] == "\\":
                    index += 2
                    continue
                if body[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "#":
            while index < len(body) and body[index] != "\n":
                index += 1
            continue
        if char in ("{", "["):
            depth += 1
            index += 1
            continue
        if char in ("}", "]"):
            depth -= 1
            index += 1
            continue
        index += 1
    return names


def scan_toml_mcp_servers(text: str) -> Dict[str, str]:
    """Return ``{server_name: raw_text}`` for every ``mcp_servers`` entry.

    Only names and the raw text needed for product detection are extracted;
    values are never rewritten here, so every existing field is preserved.
    """
    lines = [_strip_toml_comment(line) for line in text.splitlines()]
    entries: Dict[str, List[str]] = {}
    current = ""
    in_parent = False
    for line in lines:
        match = _TOML_CHILD_HEADER.match(line)
        if match:
            current = _key_from_match(match)
            entries.setdefault(current, []).append(line)
            in_parent = False
            continue
        if _TOML_ANY_HEADER.match(line):
            in_parent = bool(_TOML_PARENT_HEADER.match(line))
            current = ""
            continue
        if in_parent:
            match = _TOML_INLINE_ENTRY.match(line)
            if match:
                entries.setdefault(_key_from_match(match), []).append(line)
        dotted = _TOML_DOTTED_KEY.match(line)
        if dotted:
            entries.setdefault(_key_from_match(dotted), []).append(line)
        elif current:
            entries[current].append(line)
    cleaned = "\n".join(lines)
    span = _root_inline_span(cleaned)
    if span:
        body = cleaned[span[0] : span[1]]
        for name in _inline_table_names(body):
            entries.setdefault(name, []).append(body)
    return dict((name, "\n".join(parts)) for name, parts in entries.items())


def is_product_entry(raw_text: str, mcp_url: str) -> bool:
    """Recognise an entry written by this product (URL or explicit marker)."""
    if mcp_url and mcp_url in raw_text:
        return True
    return any(marker in raw_text for marker in PRODUCT_MARKERS)


def free_server_name(desired: str, existing_names: Iterable[str]) -> str:
    """Allocate a collision-free name without touching unrelated entries."""
    taken = set(existing_names)
    if desired not in taken:
        return desired
    index = 2
    while "%s-%d" % (desired, index) in taken:
        index += 1
    return "%s-%d" % (desired, index)


def mcp_config_path_for(platform_name: str, home: str, env: Optional[dict] = None) -> Path:
    """Resolve a Claude Desktop MCP config path for a simulated platform.

    ``platform_name`` is explicit so callers and tests never depend on the host
    OS. This is a path resolver only; it never reads or writes a real config.
    """
    env = env or {}
    user_home = Path(home)
    if platform_name == "win32":
        base = Path(env.get("APPDATA", str(user_home / "AppData" / "Roaming")))
        return base / "Claude" / "claude_desktop_config.json"
    if platform_name == "darwin":
        return user_home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if platform_name == "linux":
        base = Path(env.get("XDG_CONFIG_HOME", str(user_home / ".config")))
        return base / "Claude" / "claude_desktop_config.json"
    raise ValueError("Unsupported platform: %s" % platform_name)


def _toml_quote(value: str) -> str:
    """JSON string escaping is also valid for TOML basic strings."""
    return json.dumps(value)


def _toml_key(name: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return name
    return _toml_quote(name)


def _build_toml_content(text: str, chosen: str, is_upgrade: bool, mcp_url: str) -> Tuple[bool, str]:
    """Append (or insert) our entry while preserving all existing text."""
    if is_upgrade:
        # An existing product entry keeps its identity and every field verbatim.
        return False, text
    span = _root_inline_span(text)
    if span:
        body = text[span[0] : span[1]]
        separator = ", " if body.strip() else ""
        addition = "%s%s = { url = %s }" % (separator, _toml_key(chosen), _toml_quote(mcp_url))
        return True, text[: span[1]] + addition + text[span[1] :]
    suffix = "" if (not text or text.endswith("\n")) else "\n"
    entry = "\n[mcp_servers.%s]\nurl = %s\n" % (_toml_key(chosen), _toml_quote(mcp_url))
    return True, text + suffix + entry


def _build_json_content(text: str, parsed: Any, chosen: str, mcp_url: str) -> Tuple[bool, str]:
    data = parsed if isinstance(parsed, dict) else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a JSON object")
    existing = servers.get(chosen)
    entry = {"url": mcp_url}
    if isinstance(existing, dict):
        entry = dict(existing)
        entry["url"] = mcp_url
    servers[chosen] = entry
    content = json.dumps(data, indent=2) + "\n"
    return content != text, content


def plan_mcp_config(config_path: Path, desired_name: str, mcp_url: str) -> dict:
    """Build a non-mutating plan for adding/updating our MCP server entry.

    The chosen name is computed once here and reused by both the dry-run text
    and the success message, so the two can never disagree.
    """
    path = Path(config_path)
    fmt = "toml" if path.suffix.lower() == ".toml" else "json"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    parsed: Any = None
    if fmt == "toml":
        entries = scan_toml_mcp_servers(text)
    else:
        parsed = json.loads(text) if text.strip() else {"mcpServers": {}}
        if not isinstance(parsed, dict):
            raise ValueError("MCP config must be a JSON object")
        servers = parsed.get("mcpServers") or {}
        entries = dict((str(name), json.dumps(value, sort_keys=True)) for name, value in servers.items())
    product_names = [name for name in entries if is_product_entry(entries[name], mcp_url)]
    if product_names:
        chosen = desired_name if desired_name in product_names else product_names[0]
        is_upgrade = True
    else:
        chosen = free_server_name(desired_name, entries.keys())
        is_upgrade = False
    if fmt == "toml":
        changed, content = _build_toml_content(text, chosen, is_upgrade, mcp_url)
    else:
        changed, content = _build_json_content(text, parsed, chosen, mcp_url)
    if changed:
        dry_run_text = 'Would configure MCP server "%s" in %s' % (chosen, path)
        success_text = 'Configured MCP server "%s" in %s' % (chosen, path)
    else:
        dry_run_text = 'No change: MCP server "%s" is already configured in %s' % (chosen, path)
        success_text = 'MCP server "%s" is already configured in %s' % (chosen, path)
    return {
        "path": path,
        "format": fmt,
        "chosen_name": chosen,
        "desired_name": desired_name,
        "is_upgrade": is_upgrade,
        "changed": changed,
        "content": content,
        "existing_names": sorted(entries.keys()),
        "dry_run_text": dry_run_text,
        "success_text": success_text,
    }


def apply_mcp_config(plan: dict, dry_run: bool = False) -> str:
    """Apply *plan* and return the chosen name. Errors propagate; no fake success."""
    if dry_run or not plan["changed"]:
        return plan["chosen_name"]
    path = plan["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan["content"], encoding="utf-8")
    return plan["chosen_name"]


def write_mcp_snippets(out_dir: Path, server_name: str, mcp_url: str) -> None:
    payload = {"mcpServers": {server_name: {"url": mcp_url}}}
    write_json(out_dir / "mcp-streamable-http.json", payload)

    smoke_prompt = """Use the Blender MCP server. First call dcc_capability_manifest with loaded_only=false.
Then load the blender-geometry skill, create a sphere named mcp_setup_smoke_sphere
with radius 2, list scene objects, and tell me the MCP URL and created object name.
Use typed tools where available and avoid execute_python unless no typed tool fits.
"""
    smoke_path = out_dir / "smoke-prompt.txt"
    smoke_path.write_text(smoke_prompt, encoding="utf-8")
    print("Wrote %s" % smoke_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--blender-python",
        "--python",
        dest="blender_python",
        help="Full path to Blender's bundled Python interpreter.",
    )
    parser.add_argument(
        "--source",
        choices=["local", "pypi"],
        default="local",
        help="Install from this checkout or from PyPI. Default: local.",
    )
    parser.add_argument(
        "--mcp-url",
        default=DEFAULT_MCP_URL,
        help="MCP URL to write into generated host config. Default: %s." % DEFAULT_MCP_URL,
    )
    parser.add_argument(
        "--server-name",
        default="blender",
        help="MCP server name in generated config. Default: blender.",
    )
    parser.add_argument(
        "--out-dir",
        default=".dcc-mcp/agent-setup",
        help="Directory for generated MCP snippets. Default: .dcc-mcp/agent-setup.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Only verify imports and write MCP snippets.",
    )
    parser.add_argument(
        "--user",
        dest="user_install",
        action="store_true",
        help="Install into the user site; launch Blender with --python-use-system-env.",
    )
    parser.add_argument(
        "--startup-scripts-dir",
        help="Override Blender's per-user scripts directory (the parent of startup/).",
    )
    parser.add_argument(
        "--mcp-config",
        help="Existing MCP host config (JSON or TOML) to merge into instead of replacing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --mcp-config, print the planned change and selected name without writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = find_repo_root()
    out_dir = (repo_root / args.out_dir).resolve()

    print("Repository: %s" % repo_root)
    print("MCP URL: %s" % args.mcp_url)

    config_path = Path(args.mcp_config).expanduser() if args.mcp_config else None
    plan = None
    if config_path is not None:
        plan = plan_mcp_config(config_path, args.server_name, args.mcp_url)

    if args.dry_run:
        if plan is not None:
            print(plan["dry_run_text"])
        else:
            print("Dry run: would write MCP snippets to %s (no files written)." % out_dir)
        return 0

    blender_python = resolve_blender_python(args.blender_python)
    print("Blender Python: %s" % blender_python)

    install_package(
        blender_python,
        args.source,
        repo_root,
        args.skip_install,
        user_install=args.user_install,
    )
    if not args.skip_install:
        verify_import(blender_python)
    startup_path = install_startup_script(blender_python, args.startup_scripts_dir)
    snippet_name = plan["chosen_name"] if plan is not None else args.server_name
    write_mcp_snippets(out_dir, snippet_name, args.mcp_url)
    if plan is not None:
        apply_mcp_config(plan)
        print(plan["success_text"])

    print("")
    print("Next:")
    launch_command = " ".join(blender_launch_command("blender", user_install=args.user_install))
    print("1. Open Blender with: %s" % launch_command)
    print("2. The installed startup script starts DCC MCP Blender automatically.")
    print("3. Configure the MCP host with %s." % (out_dir / "mcp-streamable-http.json"))
    print("4. Run the smoke prompt in %s." % (out_dir / "smoke-prompt.txt"))
    print("Startup script: %s" % startup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
