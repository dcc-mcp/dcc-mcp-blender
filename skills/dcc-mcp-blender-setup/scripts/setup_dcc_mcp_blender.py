"""Prepare a Blender bundled-Python environment for dcc-mcp-blender MCP use."""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

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
        '(e.g. "C:\\Program Files\\Blender Foundation\\Blender 4.2\\4.2\\python\\bin\\python.exe"), '
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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = find_repo_root()
    blender_python = resolve_blender_python(args.blender_python)
    out_dir = (repo_root / args.out_dir).resolve()

    print("Repository: %s" % repo_root)
    print("Blender Python: %s" % blender_python)
    print("MCP URL: %s" % args.mcp_url)

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
    write_mcp_snippets(out_dir, args.server_name, args.mcp_url)

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
