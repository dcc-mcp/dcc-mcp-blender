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


DEFAULT_MCP_URL = "http://127.0.0.1:8765/mcp"


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


def install_package(blender_python: Path, source: str, repo_root: Path, skip_install: bool) -> None:
    if skip_install:
        print("Skipping pip install because --skip-install was passed.")
        return

    run([str(blender_python), "-m", "ensurepip", "--upgrade"])
    run([str(blender_python), "-m", "pip", "install", "--upgrade", "pip"])

    # dcc-mcp-blender ships no optional install extras (no `[sidecar]`); install
    # the package plainly. The dcc-mcp-core dependency is resolved transitively.
    if source == "local":
        run([str(blender_python), "-m", "pip", "install", "-e", "."], cwd=repo_root)
    elif source == "pypi":
        run([str(blender_python), "-m", "pip", "install", "--upgrade", "dcc-mcp-blender"])
    else:
        raise SystemExit("Unknown source: %s" % source)


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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = find_repo_root()
    blender_python = resolve_blender_python(args.blender_python)
    out_dir = (repo_root / args.out_dir).resolve()

    print("Repository: %s" % repo_root)
    print("Blender Python: %s" % blender_python)
    print("MCP URL: %s" % args.mcp_url)

    install_package(blender_python, args.source, repo_root, args.skip_install)
    if not args.skip_install:
        verify_import(blender_python)
    write_mcp_snippets(out_dir, args.server_name, args.mcp_url)

    print("")
    print("Next:")
    print("1. Open Blender.")
    print("2. Edit > Preferences > Extensions > Install from Disk (the release ZIP), then enable 'DCC MCP Blender'.")
    print("3. Configure the MCP host with %s." % (out_dir / "mcp-streamable-http.json"))
    print("4. Run the smoke prompt in %s." % (out_dir / "smoke-prompt.txt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
