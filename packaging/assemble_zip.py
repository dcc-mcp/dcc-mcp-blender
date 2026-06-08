"""Assemble a Blender addon ZIP package for dcc-mcp-blender.

This script:
1. Resolves the latest compatible dcc-mcp-core version from PyPI (>= MIN_CORE_VERSION).
2. Downloads the best platform wheel (prefer ``cp38-abi3-*`` — PyPI does not ship
   ``cp311-cp311-*`` builds; Blender 4.x Python still loads stable-ABI wheels).
3. Copies the ``dcc-mcp-core`` **wheel** into ``wheels/`` and records it in
   ``blender_manifest.toml`` under ``wheels = [...]`` so Blender installs it into
   the extension's isolated ``site-packages`` (no ``sys.path`` hacks, no loose
   ``dcc_mcp_core/`` tree — required for Blender 4.2+ extensions policy).
4. Bundles the adapter modules and skills directly in the add-on package root.
5. Produces ``dcc_mcp_blender_addon_{platform}_v{version}.zip`` — install via
   **Edit → Preferences → Extensions → Install from Disk** (recommended) or
   Blender's extension package installer.

Version strings in ``pyproject.toml``, ``src/dcc_mcp_blender/__version__.py``, and
``packaging/addon_entry/blender_manifest.toml`` are maintained by **release-please**
only; this script reads ``pyproject.toml`` for the ZIP filename, copies the manifest
from ``addon_entry/``, then appends the ``wheels = [...]`` entry for the downloaded
``dcc-mcp-core`` wheel basename.

Usage::

    python packaging/assemble_zip.py --platform win64 --output-dir dist_addon/
    python packaging/assemble_zip.py --platform linux --output-dir dist_addon/
    python packaging/assemble_zip.py --platform macos --output-dir dist_addon/
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import tempfile
import urllib.request
import zipfile

# ── configuration ─────────────────────────────────────────────────────────────

PACKAGE_ROOT = pathlib.Path(__file__).parent.parent
SRC_DIR = PACKAGE_ROOT / "src" / "dcc_mcp_blender"
ADDON_ENTRY_DIR = PACKAGE_ROOT / "packaging" / "addon_entry"
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"

# Must stay in sync with ``pyproject.toml`` dependency floor.
MIN_CORE_VERSION = "0.18.14"
CORE_PACKAGE = "dcc-mcp-core"
ADDON_PLATFORMS = ("win64", "linux", "macos")

# PyPI ships ``cp38-abi3-*`` wheels (stable ABI) for win/linux/macos — not cp311-tagged wheels.
# Match platform first, then prefer stable abi3 builds.

PYPI_URL = "https://pypi.org/pypi/{package}/json"

# Never bundle mistaken local trees (e.g. accidental wheel extracts under src/).
_SKIPPED_TOP_LEVEL_NAMES = frozenset({"dcc_mcp_blender", "dcc_mcp_core", "__pycache__", "__init__.py"})


def _ignore_for_addon_copy(path: str, names: list[str]) -> set[str]:
    """Skip junk subtrees and bytecode when staging the addon."""
    ignored: set[str] = set()
    try:
        if pathlib.Path(path).resolve() == SRC_DIR.resolve():
            ignored.update(n for n in names if n in _SKIPPED_TOP_LEVEL_NAMES)
    except OSError:
        pass
    ignored.update(n for n in names if n == "__pycache__" or n.endswith(".pyc"))
    return ignored


def _verify_skills_payload(staged_pkg: pathlib.Path) -> None:
    """Fail fast when the bundled skill tree is incomplete."""
    skills_dir = staged_pkg / "skills"
    if not skills_dir.is_dir():
        raise RuntimeError(f"Missing skills directory after copy: {skills_dir}")
    skill_manifests = list(skills_dir.glob("*/SKILL.md"))
    if len(skill_manifests) < 10:
        raise RuntimeError(
            f"Expected at least 10 bundled skills (SKILL.md), found {len(skill_manifests)} under {skills_dir}"
        )
    missing_tools = [
        skill_md.parent.name for skill_md in skill_manifests if not (skill_md.parent / "tools.yaml").is_file()
    ]
    if missing_tools:
        raise RuntimeError(f"Missing tools.yaml for bundled skills: {', '.join(sorted(missing_tools))}")


def _copy_adapter_package_into_addon_root(addon_dir: pathlib.Path) -> None:
    """Copy adapter modules into the add-on package root.

    The release add-on itself is the top-level ``dcc_mcp_blender`` package. If
    the adapter package is copied below another ``dcc_mcp_blender/`` directory,
    Blender imports the add-on entrypoint but ``dcc_mcp_blender.server`` cannot
    resolve from a clean extension install.
    """
    for child in SRC_DIR.iterdir():
        if child.name in _SKIPPED_TOP_LEVEL_NAMES:
            continue
        dest = addon_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, ignore=_ignore_for_addon_copy, dirs_exist_ok=False)
        else:
            shutil.copy2(child, dest)


def _version_tuple_from_string(version: str) -> tuple[int, int, int]:
    """Return a Blender ``bl_info`` version tuple from a PEP 440-ish version."""
    release = version.split("+", 1)[0].split("-", 1)[0]
    parts = (release.split(".") + ["0", "0", "0"])[:3]
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise RuntimeError(f"Could not render Blender bl_info version from {version!r}") from exc


# ── helpers ────────────────────────────────────────────────────────────────────


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        import json

        return json.loads(resp.read())


def resolve_core_version(min_version: str = MIN_CORE_VERSION) -> str:
    """Return the latest dcc-mcp-core version >= min_version."""
    data = _fetch_json(PYPI_URL.format(package=CORE_PACKAGE))
    from packaging.version import Version

    available = [Version(v) for v in data["releases"].keys() if not Version(v).is_prerelease]
    min_ver = Version(min_version)
    compatible = [v for v in available if v >= min_ver and v < Version("1.0.0")]
    if not compatible:
        raise RuntimeError(f"No compatible {CORE_PACKAGE} release found (>={min_version},<1.0.0)")
    best = sorted(compatible)[-1]
    print(f"Resolved {CORE_PACKAGE} version: {best}")
    return str(best)


def _wheel_matches_platform(filename: str, platform: str) -> bool:
    if not filename.endswith(".whl"):
        return False
    if platform == "win64":
        return "win_amd64" in filename or "win32" in filename
    if platform == "linux":
        return "linux" in filename and ("x86_64" in filename or "aarch64" in filename)
    if platform == "macos":
        return "macosx" in filename
    return False


def _wheel_rank(filename: str) -> tuple[int, str]:
    """Lower tuple sorts first (more desirable)."""
    if "cp38-abi3" in filename:
        pri = 0
    elif "abi3" in filename:
        pri = 1
    elif "cp312" in filename:
        pri = 2
    elif "cp311" in filename:
        pri = 3
    elif "cp310" in filename:
        pri = 4
    elif "py3-none-any" in filename or "py310-none-any" in filename or "py311-none-any" in filename:
        pri = 5
    else:
        pri = 50
    return (pri, filename)


def pick_core_wheel_file(release_files: list[dict], platform: str) -> dict | None:
    """Return the single best PyPI file dict for *platform*, or ``None``."""
    candidates = [f for f in release_files if _wheel_matches_platform(f.get("filename", ""), platform)]
    if not candidates:
        return None
    candidates.sort(key=lambda f: _wheel_rank(f["filename"]))
    return candidates[0]


def download_core_wheel(version: str, platform: str, dest_dir: pathlib.Path) -> pathlib.Path:
    """Download exactly one dcc-mcp-core wheel for *platform*.

    Raises:
        RuntimeError: When no compatible wheel exists on PyPI for this platform/version.
    """
    data = _fetch_json(PYPI_URL.format(package=CORE_PACKAGE))
    release_files = data["releases"].get(version, [])
    pick = pick_core_wheel_file(release_files, platform)
    if pick is None:
        sample = [f["filename"] for f in release_files if f["filename"].endswith(".whl")][:12]
        raise RuntimeError(
            f"No {CORE_PACKAGE} wheel for platform={platform!r} at version {version!r}. PyPI wheel sample: {sample}"
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = pick["filename"]
    url = pick["url"]
    dest = dest_dir / filename
    if not dest.exists():
        print(f"  Downloading: {filename}")
        urllib.request.urlretrieve(url, dest)  # noqa: S310
    else:
        print(f"  Cached: {filename}")
    return dest


def extract_wheel(wheel_path: pathlib.Path, dest_dir: pathlib.Path) -> None:
    """Extract a wheel into dest_dir, skipping .dist-info."""
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for member in zf.namelist():
            if ".dist-info/" in member:
                continue
            zf.extract(member, dest_dir)


def get_package_version() -> str:
    """Read version from pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not find version in pyproject.toml")
    return m.group(1)


def _read_assigned_quoted_string(path: pathlib.Path, key: str) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    if not m:
        raise RuntimeError(f'Could not find {key} = "…" in {path}')
    return m.group(1)


def assert_release_please_versions_aligned() -> None:
    """Fail fast when version sources drift (all bumps go through release-please)."""
    py_v = get_package_version()
    mod_v = _read_assigned_quoted_string(PACKAGE_ROOT / "src" / "dcc_mcp_blender" / "__version__.py", "__version__")
    man_v = _read_assigned_quoted_string(ADDON_ENTRY_DIR / "blender_manifest.toml", "version")
    if py_v == mod_v == man_v:
        return
    raise RuntimeError(
        "Version mismatch — keep pyproject.toml, __version__.py, and blender_manifest.toml "
        "in sync via release-please only:\n"
        f"  pyproject.toml:        {py_v!r}\n"
        f"  __version__.py:        {mod_v!r}\n"
        f"  blender_manifest.toml: {man_v!r}"
    )


def assemble(platform: str, output_dir: pathlib.Path) -> pathlib.Path:
    """Assemble the addon ZIP for the given platform.

    Returns the path to the created ZIP file.
    """
    assert_release_please_versions_aligned()
    version = get_package_version()
    zip_name = f"dcc_mcp_blender_addon_{platform}_v{version}.zip"
    zip_path = output_dir / zip_name

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        addon_dir = tmp_dir / "dcc_mcp_blender"
        addon_dir.mkdir()

        # 1) Copy dcc_mcp_blender package source into the add-on package root.
        print("Copying dcc_mcp_blender package...")
        _copy_adapter_package_into_addon_root(addon_dir)
        _verify_skills_payload(addon_dir)

        # 2) Download and extract dcc-mcp-core
        print(f"Resolving {CORE_PACKAGE}...")
        core_version = resolve_core_version()
        wheels_dir = tmp_dir / "wheels"
        wheel = download_core_wheel(core_version, platform, wheels_dir)
        wheels_out = addon_dir / "wheels"
        wheels_out.mkdir(parents=True, exist_ok=True)
        staged_wheel = wheels_out / wheel.name
        shutil.copy2(wheel, staged_wheel)
        print(f"  Bundled wheel: {staged_wheel.relative_to(addon_dir)}")

        # 3) Stage add-on root: ``__init__.py`` + ``blender_manifest.toml`` (4.2+ extensions)
        _stage_addon_entry(addon_dir, version=version)
        _inject_wheels_into_manifest(addon_dir / "blender_manifest.toml", [wheel.name])

        # 4) Zip the extension package contents at archive root. Blender's
        # extension installer expects ``blender_manifest.toml`` at ZIP root.
        print(f"Creating {zip_name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in addon_dir.rglob("*"):
                if file.is_file() and "__pycache__" not in str(file):
                    arcname = file.relative_to(addon_dir)
                    zf.write(file, arcname)

    print(f"Created: {zip_path}")
    return zip_path


def _inject_wheels_into_manifest(manifest_path: pathlib.Path, wheel_basenames: list[str]) -> None:
    """Write ``wheels = [...]`` for Blender's extension wheel installer.

    See https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html
    """
    text = manifest_path.read_text(encoding="utf-8")
    text = re.sub(r"\n+wheels\s*=\s*\[.*?\]\s*", "\n", text, flags=re.DOTALL)
    lines = [f'    "./wheels/{name}"' for name in wheel_basenames]
    block = "\nwheels = [\n" + ",\n".join(lines) + ",\n]\n"
    first_table = re.search(r"\n\[[^\]]+\]", text)
    if first_table is None:
        rendered = text.rstrip() + block
    else:
        rendered = text[: first_table.start()].rstrip() + block + text[first_table.start() :]
    manifest_path.write_text(rendered, encoding="utf-8")


def _render_static_bl_info_version(init_path: pathlib.Path, version: str) -> None:
    """Render the staged add-on entry's static ``bl_info['version']`` tuple."""
    major, minor, patch = _version_tuple_from_string(version)
    text = init_path.read_text(encoding="utf-8")
    rendered, count = re.subn(
        r'("version"\s*:\s*)\(\s*(\d+)\s*,\s*[^\d)]*?(\d+)\s*,\s*[^\d)]*?(\d+)\s*[^\d)]*?\)',
        rf"\1({major}, {minor}, {patch})",
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(f"Could not find static bl_info version tuple in {init_path}")
    init_path.write_text(rendered, encoding="utf-8")


def _stage_addon_entry(addon_dir: pathlib.Path, *, version: str) -> None:
    """Copy packaged add-on entry (menu, manifest) into the staged ZIP root."""
    init_src = ADDON_ENTRY_DIR / "__init__.py"
    manifest_src = ADDON_ENTRY_DIR / "blender_manifest.toml"
    if not init_src.is_file():
        raise RuntimeError(f"Missing add-on entry __init__.py: {init_src}")
    if not manifest_src.is_file():
        raise RuntimeError(f"Missing blender_manifest.toml: {manifest_src}")

    shutil.copy2(init_src, addon_dir / "__init__.py")
    _render_static_bl_info_version(addon_dir / "__init__.py", version)
    shutil.copy2(manifest_src, addon_dir / "blender_manifest.toml")


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble Blender addon ZIP for dcc-mcp-blender")
    parser.add_argument(
        "--platform",
        choices=list(ADDON_PLATFORMS),
        default="linux",
        help="Target platform (default: linux)",
    )
    parser.add_argument(
        "--output-dir",
        default="dist_addon",
        help="Output directory for the ZIP file (default: dist_addon/)",
    )
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir)
    zip_path = assemble(platform=args.platform, output_dir=output_dir)
    print(f"\nDone: {zip_path}")


if __name__ == "__main__":
    main()
