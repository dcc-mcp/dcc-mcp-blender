"""E2E test: Blender can actually enable the packaged add-on.

Unlike ``tests/test_addon_packaging.py`` (which calls ``register()`` against a
fake ``bpy``), this test drives Blender's real add-on manager end to end:

    stage ``packaging/addon_entry`` as a legacy ``scripts/addons`` add-on
    -> ``bpy.ops.preferences.addon_enable``  (imports it + calls ``register()``)
    -> assert the operator/menu classes are registered
    -> ``bpy.ops.preferences.addon_disable`` (calls ``unregister()``)

This is the "can Blender enable the add-on?" guard and exercises the same
``register()`` path Blender runs on production auto-load. The legacy ``bl_info``
install path enables on every matrix version (3.6 LTS .. 4.4); the 4.2+
extension manifest is verified separately by the packaging tests.

Run::

    blender --background --python -m pytest tests/e2e/test_addon_enable_e2e.py -- -v
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available — run inside Blender Python interpreter")

if sys.platform == "win32":
    # The add-on's register() starts the MCP server; Blender's bundled libuv
    # trips a UV_HANDLE_CLOSING assertion on Windows background runs (same reason
    # test_server_e2e.py skips). Linux + macOS cover the real enable path.
    pytest.skip(
        "addon enable starts the server; Windows server lifecycle is covered elsewhere", allow_module_level=True
    )

pytestmark = pytest.mark.e2e

ADDON_ENTRY = Path(__file__).parents[2] / "packaging" / "addon_entry" / "__init__.py"
ADDON_MODULE = "dcc_mcp_blender_enable_e2e"


def _addon_dir() -> Path:
    """User ``scripts/addons`` directory Blender scans for legacy add-ons."""
    return Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))


def _stage_addon() -> Path:
    """Copy the packaged add-on entry into a discoverable add-on package."""
    dest = _addon_dir() / ADDON_MODULE
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    # Copy the whole directory so we get blender_manifest.toml too (required for 4.2+)
    for item in ADDON_ENTRY.parent.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
    return dest


def _cleanup(dest: Path) -> None:
    import addon_utils  # noqa: PLC0415

    try:
        bpy.ops.preferences.addon_disable(module=ADDON_MODULE)
    except Exception:  # noqa: BLE001
        pass
    addon_utils.modules(refresh=True)
    sys.modules.pop(ADDON_MODULE, None)
    shutil.rmtree(dest, ignore_errors=True)


def test_blender_enables_packaged_addon():
    """The packaged add-on enables through Blender's real add-on manager."""
    import traceback  # noqa: PLC0415

    import addon_utils  # noqa: PLC0415

    # Ensure the real package owns ``dcc_mcp_blender`` in sys.modules so the
    # add-on entry's self-aliasing guard stays a no-op (it uses setdefault).
    import dcc_mcp_blender  # noqa: F401, PLC0415

    import sys
    print(f"\n[DEBUG] sys.path: {sys.path}", file=sys.__stdout__)
    print(f"[DEBUG] script_paths: {bpy.utils.script_paths()}", file=sys.__stdout__)
    print(f"[DEBUG] user_addons: {_addon_dir()}", file=sys.__stdout__)
    sys.__stdout__.flush()

    assert ADDON_ENTRY.is_file(), f"add-on entry missing: {ADDON_ENTRY}"

    dest = _stage_addon()
    print(f"[DEBUG] Staged addon to: {dest}", file=sys.__stdout__)
    print(f"[DEBUG] Staged files: {list(dest.iterdir())}", file=sys.__stdout__)
    sys.__stdout__.flush()

    try:
        bpy.ops.preferences.addon_refresh()
        addon_utils.modules(refresh=True)

        # Check if it's even visible to addon_utils
        matches = [m for m in addon_utils.modules() if m.__name__ == ADDON_MODULE]
        if not matches:
            print(f"[ERROR] {ADDON_MODULE} not found in addon_utils.modules() after refresh", file=sys.__stdout__)
            all_names = [m.__name__ for m in addon_utils.modules()]
            print(f"[DEBUG] First 10 modules: {all_names[:10]}", file=sys.__stdout__)
            sys.__stdout__.flush()

        print(f"[DEBUG] Enabling {ADDON_MODULE}...", file=sys.__stdout__)
        sys.__stdout__.flush()
        try:
            res = bpy.ops.preferences.addon_enable(module=ADDON_MODULE)
            print(f"[DEBUG] addon_enable result: {res}", file=sys.__stdout__)
            sys.__stdout__.flush()
        except Exception:
            print(f"[ERROR] addon_enable raised exception:\n{traceback.format_exc()}", file=sys.__stdout__)
            sys.__stdout__.flush()
            raise

        is_enabled, is_loaded = addon_utils.check(ADDON_MODULE)
        print(f"[DEBUG] addon_utils.check: enabled={is_enabled}, loaded={is_loaded}", file=sys.__stdout__)
        sys.__stdout__.flush()

        if not is_enabled:
            # Look for the module in Blender's internal addon data to see why it failed
            from addon_utils import addon_modules_info  # noqa: PLC0415

            info = addon_modules_info().get(ADDON_MODULE)
            print(f"[DEBUG] addon_modules_info for {ADDON_MODULE}: {info}", file=sys.__stdout__)
            sys.__stdout__.flush()

        assert is_enabled, f"{ADDON_MODULE} not marked enabled after addon_enable"
        assert is_loaded, f"{ADDON_MODULE} module not loaded after addon_enable"

        # register() must have registered the operator + menu classes.
        assert hasattr(bpy.types, "DCCMCP_MT_main_menu"), "top-bar menu class not registered"
        assert hasattr(bpy.ops, "dcc_mcp") and hasattr(bpy.ops.dcc_mcp, "show_server_urls"), (
            "dcc_mcp operators not registered after enable"
        )
    except Exception:
        print(f"[FAIL] Test failed with traceback:\n{traceback.format_exc()}", file=sys.__stdout__)
        sys.__stdout__.flush()
        raise
    finally:
        _cleanup(dest)

    # After disable the operator namespace must be torn down again.
    assert not addon_utils.check(ADDON_MODULE)[1], "add-on still loaded after disable"
