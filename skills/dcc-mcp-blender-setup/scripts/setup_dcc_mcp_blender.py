"""Prepare a Blender bundled-Python environment for dcc-mcp-blender MCP use."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
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
# Product identity is always scoped to ONE server and uses the parsed, EXACT
# ``url`` value (never a raw-text substring) or an explicit product marker. A
# root inline table is split into per-server value spans, so a sibling's
# URL/marker can never be mistaken for another server's. An existing product
# entry is a no-op: its name AND every field (including its url) survive
# verbatim, and repeated runs stay idempotent.
#
# On Python 3.11+ (or with the ``tomli`` backport) a real TOML parser is
# authoritative and both the input and the merged output are validated before
# writing. On stock Python 3.7 the pure-stdlib scanner is used; it is root-scoped
# and refuses multiline strings, nested mcp_servers tables and other ambiguous
# input rather than guessing. Root inline table keys (bare or quoted) are parsed
# by the same key-path parser as the scanner, so a valid quoted-root config is
# merged in place instead of producing a duplicate declaration. Written strings
# are TOML-escaped (Unicode kept literal, control chars/DEL escaped), and writes
# are guarded against TOCTOU changes, preserve file mode/symlink target, and
# stage privately + os.replace atomically. Either way no invalid TOML is written
# and errors never fake success.

PRODUCT_MARKERS = ("dcc-mcp-blender", "dcc_mcp_blender")

_KEY_PATTERN = r"""(?:"([^"]+)"|'([^']+)'|([A-Za-z0-9_-]+))"""
_KEY_SEGMENT = re.compile(_KEY_PATTERN)
_TOML_HEADER = re.compile(r"^\s*\[\s*(.+?)\s*\]\s*$")
# A root-level key can only appear before the first table header. There is
# deliberately no separate root-inline regex: _root_inline_span parses the LHS
# with _parse_key_path so quoted keys cannot drift between scanner and builder.
_FIRST_TABLE_HEADER = re.compile(r"(?m)^[ \t]*\[")


def _string_end(text: str, start: int) -> Optional[int]:
    """Return the index just past the TOML string opened at *start*, else ``None``.

    Basic and literal single-line strings, and triple-quoted multiline strings,
    are all recognised. Only basic (double-quoted) strings interpret a backslash
    as an escape; TOML literal strings do not, so a trailing backslash before a
    closing single quote is not mistaken for an escaped quote.
    """
    quote = text[start]
    if quote not in ('"', "'"):
        return None
    basic = quote == '"'
    length = len(text)
    if text.startswith(quote * 3, start):
        delimiter = quote * 3
        index = start + 3
        while index < length:
            if basic and text[index] == "\\":
                index += 2
                continue
            if text.startswith(delimiter, index):
                return index + 3
            index += 1
        return None
    index = start + 1
    while index < length:
        char = text[index]
        if basic and char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        if char == "\n":
            return None  # a single-line string cannot contain a raw newline
        index += 1
    return None


def _decode_toml_string(token: str) -> str:
    """Decode one TOML/JSON string token for identity comparisons."""
    if token.startswith("'"):
        if token.startswith("'''") and token.endswith("'''"):
            inner = token[3:-3]
            return inner[1:] if inner.startswith("\n") else inner
        return token[1:-1]
    try:
        # JSON escapes are a subset of TOML basic-string escapes; this also
        # decodes \uXXXX in quoted keys so the fallback matches a real parser.
        return json.loads(token)
    except (ValueError, TypeError):
        if token.startswith('"""') and token.endswith('"""'):
            inner = token[3:-3]
            return inner[1:] if inner.startswith("\n") else inner
        return token[1:-1]


def _iter_string_leaves(value: Any) -> Iterable[str]:
    """Yield every string scalar inside a parsed (JSON-like) value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_string_leaves(item)


def _toml_fragment_identity(text: str) -> Tuple[Optional[str], List[str]]:
    """Return ``(url_value, string_values)`` for one scoped TOML fragment.

    A small string-aware tokenizer finds a ``url`` key (bare, dotted or quoted,
    followed by ``=``/``:``) and its EXACT string value, and collects every
    decoded string for marker detection. Strings are skipped wholesale, so a
    url-like word inside a value is never treated as a field key. This is used
    only by the Python 3.7 fallback scanner, where no real TOML parser exists.
    """
    tokens: List[Tuple[str, str]] = []
    values: List[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "#":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if char in ('"', "'"):
            end = _string_end(text, index)
            if end is None:
                break
            decoded = _decode_toml_string(text[index:end])
            tokens.append(("str", decoded))
            values.append(decoded)
            index = end
            continue
        if char in "=:":
            tokens.append(("sep", char))
        elif char in ",{}[]\n":
            tokens.append(("punct", char))
        elif not char.isspace():
            end = index
            while end < length and (text[end].isalnum() or text[end] in "_-."):
                end += 1
            tokens.append(("word", text[index:end]))
            index = end
            continue
        index += 1
    url: Optional[str] = None
    for position, (kind, value) in enumerate(tokens):
        is_url_key = (kind == "word" and value.split(".")[-1] == "url") or (kind == "str" and value == "url")
        if is_url_key and position + 2 < len(tokens):
            if tokens[position + 1][0] == "sep" and tokens[position + 2][0] == "str":
                url = tokens[position + 2][1]
                break
    return url, values


def _entry_identity(raw_text: str) -> Tuple[Optional[str], List[str]]:
    """Return ``(url_value, string_values)`` for one scoped server entry.

    ``raw_text`` is either a JSON-serialized server value (authoritative parser
    or JSON config) or a raw TOML fragment (Python 3.7 fallback). For JSON the
    parsed ``url`` field is read directly, so a value such as ``.../mcp-other``
    is never mistaken for ``.../mcp`` by a substring test.
    """
    try:
        parsed = json.loads(raw_text)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        url = parsed.get("url")
        return (url if isinstance(url, str) else None), list(_iter_string_leaves(parsed))
    return _toml_fragment_identity(raw_text)


def _key_from_match(match: Any) -> str:
    """Return the captured TOML key (quoted or bare) from a regex match.

    Double-quoted basic keys are decoded (e.g. ``"bl\\u0065nder"`` -> ``blender``)
    so the Python 3.7 fallback resolves the same key as an authoritative parser.
    """
    if match.group(1) is not None:
        return _decode_toml_string('"' + match.group(1) + '"')
    if match.group(2) is not None:
        return match.group(2)
    return match.group(3)


def _strip_toml_comment(line: str) -> str:
    """Remove a trailing ``#`` comment while honouring TOML string boundaries."""
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if char in ('"', "'"):
            end = _string_end(line, index)
            if end is None:
                # Unterminated string on this line; multiline strings are
                # refused before the line-oriented fallback scanner runs.
                return line
            index = end
            continue
        if char == "#":
            return line[:index]
        index += 1
    return line


def _balanced_body(text: str, open_index: int) -> Optional[str]:
    """Return the body of the inline table opened at *open_index*.

    Basic/literal/triple-quoted strings are skipped as whole tokens, so a
    literal string ending in a backslash, or a multiline triple-quoted string,
    cannot hide the closing ``}`` from the brace counter.
    """
    depth = 0
    index = open_index
    length = len(text)
    while index < length:
        char = text[index]
        if char in ('"', "'"):
            end = _string_end(text, index)
            if end is None:
                return None
            index = end
            continue
        if char == "#":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
        index += 1
    return None


def _root_inline_open_brace(line: str, eq: int, offset: int) -> int:
    """Return the absolute index of the inline-table ``{`` after *eq*, or -1.

    Strings are skipped as whole tokens and a trailing comment ends the line,
    so a ``{`` inside a string or comment is never mistaken for the table.
    """
    index = eq + 1
    length = len(line)
    while index < length:
        char = line[index]
        if char in ('"', "'"):
            end = _string_end(line, index)
            if end is None:
                return -1
            index = end
            continue
        if char == "#":
            return -1
        if char == "{":
            return offset + index
        index += 1
    return -1


def _root_inline_span(text: str) -> Optional[Tuple[int, int]]:
    """Return ``(body_start, body_end)`` for a ROOT ``mcp_servers = {...}``.

    The LHS key is resolved with ``_parse_key_path`` -- the SAME key-path
    parser used by ``scan_toml_mcp_servers`` -- so bare, 'single-quoted',
    "double-quoted" and escaped-quoted spellings of ``mcp_servers`` are all
    recognised identically by the scanner and the builder. A root-level key
    can only sit before the first table header; an ``mcp_servers = {...}``
    under ``[profiles.dev]`` belongs to that table and must not be treated as
    the root config (Python 3.7 fallback correctness).
    """
    header = _FIRST_TABLE_HEADER.search(text)
    root_text = text[: header.start()] if header else text
    offset = 0
    for line in root_text.splitlines(keepends=True):
        eq = _top_level_eq(line)
        if eq >= 0:
            try:
                is_root_key = _parse_key_path(line[:eq]) == ["mcp_servers"]
            except ValueError:
                is_root_key = False
            if is_root_key:
                open_index = _root_inline_open_brace(line, eq, offset)
                if open_index >= 0:
                    body = _balanced_body(text, open_index)
                    if body is not None:
                        return open_index + 1, open_index + 1 + len(body)
        offset += len(line)
    return None


def _inline_table_names(body: str) -> List[str]:
    """Return top-level keys of a TOML inline-table body.

    Nested ``{...}`` values are skipped so fields such as ``command`` are not
    mistaken for MCP server names. Strings (basic, literal and triple-quoted)
    are skipped as whole tokens via ``_string_end``.
    """
    names: List[str] = []
    key_assignment = re.compile(_KEY_PATTERN + r"\s*=")
    index = 0
    depth = 0
    while index < len(body):
        if depth == 0:
            match = key_assignment.match(body, index)
            if match:
                names.append(_key_from_match(match))
                index = match.end()
                continue
        char = body[index]
        if char in ('"', "'"):
            end = _string_end(body, index)
            if end is None:
                break
            index = end
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


def _load_toml_parser():
    """Return a real TOML parser when importable, else ``None``.

    ``tomllib`` is stdlib on 3.11+; ``tomli`` is an optional backport. The
    import is lazy and guarded, so stock Python 3.7 keeps working through the
    pure-stdlib fallback scanner.
    """
    try:
        import tomllib

        return tomllib
    except ImportError:
        pass
    try:
        import tomli

        return tomli
    except ImportError:
        return None


def _parse_toml_servers(text: str, parser: Any):
    """Authoritative, per-server scoped entries from a real TOML parser.

    Returns ``None`` when no parser is importable (Python 3.7 fallback), or a
    ``{name: scoped_text}`` dict. Each server's text is a serialization of only
    that server's own value, so product detection can never inherit a sibling's
    URL or marker. Invalid TOML is refused instead of guessed.
    """
    if parser is None:
        return None
    try:
        data = parser.loads(text)
    except ValueError as exc:
        raise ValueError("Refusing to merge invalid TOML MCP config: %s" % exc) from exc
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ValueError("Refusing to merge: mcp_servers must be a TOML table")
    return dict(
        (str(name), value if isinstance(value, str) else json.dumps(value, sort_keys=True))
        for name, value in servers.items()
    )


def _validate_toml_output(content: str, chosen: str, changed: bool, mcp_url: str, parser: Any) -> None:
    """Refuse to write a merged result that is not valid TOML or lacks our entry.

    With a real parser this is the guard against writing ``Cannot declare ...
    twice`` output. On the Python 3.7 fallback (no parser) the merged text is
    re-scanned with the scoped scanner and our entry must still be present with
    the exact URL, so a broken merge never reports success without a backstop.
    """
    if not changed:
        return
    if parser is not None:
        try:
            merged = parser.loads(content)
        except ValueError as exc:
            raise ValueError("Refusing to write invalid TOML MCP config: %s" % exc) from exc
        servers = merged.get("mcp_servers", {})
        entry = servers.get(chosen) if isinstance(servers, dict) else None
        if not isinstance(entry, dict) or entry.get("url") != mcp_url:
            raise ValueError("Refusing to write: merged config is missing the product server entry")
        return
    entries = scan_toml_mcp_servers(content)
    url, _ = _entry_identity(entries.get(chosen, ""))
    if url != mcp_url:
        raise ValueError("Refusing to write: merged config is missing the product server entry")


def _split_statements(cleaned: str) -> List[str]:
    """Split comment-stripped TOML into top-level statements.

    A statement ends at a newline outside any inline table, array or string, so
    multi-line inline tables stay inside one statement. Every string is skipped
    as a whole token via ``_string_end`` (literal strings do not treat ``\\`` as
    an escape). Unbalanced delimiters are refused rather than mis-scoped.
    """
    statements: List[str] = []
    start = 0
    depth = 0
    index = 0
    length = len(cleaned)
    while index < length:
        char = cleaned[index]
        if char in ('"', "'"):
            end = _string_end(cleaned, index)
            if end is None:
                raise ValueError("Unbalanced string in MCP config")
            index = end
            continue
        if char == "#":  # defensive; comments are stripped beforehand
            while index < length and cleaned[index] != "\n":
                index += 1
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced delimiters in MCP config")
        elif char == "\n" and depth == 0:
            statements.append(cleaned[start:index])
            start = index + 1
        index += 1
    if depth != 0:
        raise ValueError("Unbalanced delimiters in MCP config")
    statements.append(cleaned[start:])
    return statements


def _parse_key_path(text: str) -> List[str]:
    """Split a (possibly dotted, possibly quoted) TOML key into its segments."""
    segments: List[str] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t.":
            index += 1
        if index >= length:
            break
        match = _KEY_SEGMENT.match(text, index)
        if not match:
            raise ValueError("Cannot parse TOML key path %r" % text)
        segments.append(_key_from_match(match))
        index = match.end()
    return segments


def _top_level_eq(text: str) -> int:
    """Return the index of the ``=`` separating key from value, or ``-1``."""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in ('"', "'"):
            end = _string_end(text, index)
            if end is None:
                return -1
            index = end
            continue
        if char == "=":
            return index
        index += 1
    return -1


def _split_inline_pairs(body: str) -> List[Tuple[str, str]]:
    """Split an inline-table body into ``(name, value_text)`` pairs.

    ``value_text`` is the exact slice belonging to that single server, so
    product detection never sees a sibling's fields. Nested ``{}``/``[]``,
    quoted strings and comments are honoured; unbalanced input is refused.
    """
    pairs: List[Tuple[str, str]] = []
    key_assignment = re.compile(_KEY_PATTERN + r"\s*=")
    index = 0
    length = len(body)
    while index < length:
        char = body[index]
        if char in " \t\r\n,":
            index += 1
            continue
        if char == "#":
            while index < length and body[index] != "\n":
                index += 1
            continue
        match = key_assignment.match(body, index)
        if not match:
            raise ValueError("Cannot parse inline MCP table entry")
        name = _key_from_match(match)
        index = match.end()  # just past '='
        value_start = index
        depth = 0
        while index < length:
            c = body[index]
            if c in ('"', "'"):
                end = _string_end(body, index)
                if end is None:
                    raise ValueError("Unbalanced inline MCP table")
                index = end
                continue
            if c == "#":
                while index < length and body[index] != "\n":
                    index += 1
                continue
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced inline MCP table")
            elif c == "," and depth == 0:
                break
            index += 1
        if depth != 0:
            raise ValueError("Unbalanced inline MCP table")
        pairs.append((name, body[value_start:index]))
    return pairs


def _inline_body(text: str, start: int) -> str:
    """Return the body of the inline table whose ``{`` is at/after *start*."""
    open_index = text.find("{", start)
    if open_index < 0:
        raise ValueError("Expected an inline MCP table")
    body = _balanced_body(text, open_index)
    if body is None:
        raise ValueError("Unbalanced inline MCP table")
    return body


def scan_toml_mcp_servers(text: str) -> Dict[str, str]:
    """Return ``{server_name: scoped_raw_text}`` for every ``mcp_servers`` entry.

    Each server receives only its own key/value text, so product detection can
    never inherit a sibling's URL or marker (the root-inline bug). Dotted
    subfield keys inside ``[mcp_servers]`` are recognised as well. Values are
    never rewritten here; every existing field survives verbatim.

    This is the Python 3.7 fallback scanner. It covers standard tables, quoted
    keys, inline/dotted/root-inline/dotted-subfield forms, multi-line inline
    tables and trailing comments, and raises ``ValueError`` on ambiguous or
    unbalanced input instead of guessing.

    Multiline (triple-quoted) strings and ``mcp_servers`` tables nested inside
    another table cannot be verified by this line-oriented scanner, so they are
    refused outright on Python 3.7 rather than guessed at.
    """
    if '"""' in text or "'''" in text:
        raise ValueError("Refusing ambiguous TOML: multiline strings need a real TOML parser")
    cleaned = "\n".join(_strip_toml_comment(line) for line in text.splitlines())
    entries: Dict[str, List[str]] = {}

    def add(name: str, chunk: str) -> None:
        if chunk.strip():
            entries.setdefault(name, []).append(chunk)

    mode = "root"
    current = ""
    for statement in _split_statements(cleaned):
        stripped = statement.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            header = _TOML_HEADER.match(stripped)
            if not header:
                raise ValueError("Cannot parse MCP config table header")
            segments = _parse_key_path(header.group(1))
            if segments and segments[0] == "mcp_servers":
                if len(segments) == 1:
                    mode = "parent"
                    current = ""
                else:
                    mode = "child"
                    current = segments[1]
                    add(current, stripped)
            else:
                mode = "other"
                current = ""
            continue
        eq = _top_level_eq(stripped)
        if eq < 0:
            continue
        lhs = stripped[:eq]
        rhs = stripped[eq + 1 :]
        segments = _parse_key_path(lhs)
        if not segments:
            continue
        if segments[0] == "mcp_servers":
            # A root-level mcp_servers key is only meaningful at root scope.
            # Under another table it is a DIFFERENT table: the authoritative
            # parser ignores it, so the fallback must refuse it rather than
            # merge into the wrong place.
            if mode != "root":
                raise ValueError("Refusing ambiguous TOML: nested mcp_servers needs a real TOML parser")
            if len(segments) == 1 and "{" in rhs:
                # Root inline table: split per server so no shared body leaks.
                body = _inline_body(rhs, 0)
                for name, value_text in _split_inline_pairs(body):
                    add(name, value_text)
            elif len(segments) >= 2:
                # Root dotted key: mcp_servers.blender.field = ...
                add(segments[1], statement)
            continue
        if mode == "parent":
            # Inside [mcp_servers]: the FIRST key segment is the server name.
            add(segments[0], statement)
        elif mode == "child" and current:
            add(current, statement)
        # root / non-mcp statements are ignored.
    return dict((name, "\n".join(chunks)) for name, chunks in entries.items())


def is_product_entry(raw_text: str, mcp_url: str) -> bool:
    """Recognise an entry written by this product (exact URL or explicit marker).

    ``raw_text`` is one SERVER's scoped value. The URL is compared as a parsed,
    exact value, never as a substring of the raw text: a value such as
    ``http://127.0.0.1:9765/mcp-other`` must NOT be mistaken for ``.../mcp``.
    Markers are matched against the entry's own string values only.
    """
    url, values = _entry_identity(raw_text)
    if url is not None and url == mcp_url:
        return True
    return any(marker in value for value in values for marker in PRODUCT_MARKERS)


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
    """Encode *value* as a TOML basic string.

    ``json.dumps`` is not sufficient: with ``ensure_ascii=True`` it emits
    non-BMP scalars as UTF-16 surrogate pairs, and TOML forbids surrogate code
    points in ``\\uXXXX`` escapes. Here non-ASCII scalars (e.g. emoji) stay
    literal, while the control characters TOML requires to be escaped
    (U+0000-U+0008, U+000B-U+000C, U+000E-U+001F, U+007F DEL) plus any lone
    surrogate are emitted as ``\\uXXXX``.
    """
    parts = ['"']
    for char in value:
        code = ord(char)
        if char == '"':
            parts.append('\\"')
        elif char == "\\":
            parts.append("\\\\")
        elif char == "\b":
            parts.append("\\b")
        elif char == "\t":
            parts.append("\\t")
        elif char == "\n":
            parts.append("\\n")
        elif char == "\f":
            parts.append("\\f")
        elif char == "\r":
            parts.append("\\r")
        elif code < 0x20 or code == 0x7F or 0xD800 <= code <= 0xDFFF:
            parts.append("\\u%04X" % code)
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _toml_key(name: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return name
    return _toml_quote(name)


def _build_toml_content(text: str, chosen: str, mcp_url: str) -> Tuple[bool, str]:
    """Append (or insert) a NEW entry while preserving all existing text.

    Upgrades are handled as a no-op by ``plan_mcp_config``; this function only
    ever builds content for a brand-new server name.
    """
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
    # ``chosen`` is always a free name here, so no existing entry is touched.
    # An upgrade is a no-op handled by plan_mcp_config and never reaches this
    # function, so an operator's existing ``url``/fields are never overwritten.
    servers[chosen] = {"url": mcp_url}
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
    toml_parser = None
    if fmt == "toml":
        # A real parser is authoritative when available (3.11+ / tomli); the
        # scoped stdlib scanner is the Python 3.7 fallback. Either way the
        # merged output is validated before anything is written.
        toml_parser = _load_toml_parser()
        entries = _parse_toml_servers(text, toml_parser)
        if entries is None:
            entries = scan_toml_mcp_servers(text)
    else:
        try:
            parsed = json.loads(text) if text.strip() else {"mcpServers": {}}
        except json.JSONDecodeError:
            if path.suffix.lower() != ".json":
                raise ValueError("Cannot parse %s as JSON; TOML MCP configs must use a .toml suffix" % path) from None
            raise
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
    if is_upgrade:
        # An existing product entry keeps its identity AND every field verbatim,
        # including its url. Both JSON and TOML are a no-op, so a --mcp-url
        # change never rewrites an operator's existing configuration.
        changed = False
        content = text
    elif fmt == "toml":
        changed, content = _build_toml_content(text, chosen, mcp_url)
        _validate_toml_output(content, chosen, changed, mcp_url, toml_parser)
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
        "original_text": text,
        "existing_names": sorted(entries.keys()),
        "dry_run_text": dry_run_text,
        "success_text": success_text,
    }


def apply_mcp_config(plan: dict, dry_run: bool = False) -> str:
    """Apply *plan* and return the chosen name. Errors propagate; no fake success.

    Safety properties:

    * TOCTOU guard: refuse if the file changed between planning and applying.
    * Symlinks: resolve the real target so an atomic replace updates the file,
      not the link.
    * Mode: preserve the target's permission bits (default 0o600 for new files).
    * Private staging: write to a mkstemp file in the target directory and
      os.replace it into place, cleaning up the temp on any failure.
    """
    if dry_run or not plan["changed"]:
        return plan["chosen_name"]
    path = Path(plan["path"])
    current_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if current_text != plan["original_text"]:
        raise ValueError("Refusing to write: MCP config changed since the plan was built")
    target = Path(os.path.realpath(str(path)))
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    fd, tmp = tempfile.mkstemp(prefix=".mcp-config-", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(plan["content"])
        os.chmod(tmp, mode)
        os.replace(tmp, target)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
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
    snippet_path = (out_dir / "mcp-streamable-http.json").resolve()
    if config_path is not None and config_path.resolve() == snippet_path:
        # The non-dry-run path writes this exact file as a generated snippet.
        # Merging into it would be silently overwritten by write_mcp_snippets,
        # so refuse the collision before planning anything.
        raise SystemExit("Refusing --mcp-config that points at the generated MCP snippet: %s" % snippet_path)
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
