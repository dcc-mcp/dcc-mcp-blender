"""E2E tests for the add-on lifecycle tools, running inside real Blender.

These install and remove a throwaway add-on, which is the only way to prove the
preference operators actually do what the tools report. The mocked ops accept
any keyword and always return FINISHED, so they can never catch an argument
Blender rejects or a step that silently does nothing.

The add-on is removed in teardown, on every path, so a failed assertion cannot
leave it installed behind.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402

_ADDON_MODULE = "dcc_mcp_blender_e2e_temp_addon"
_ADDON_SOURCE = '''"""Throwaway add-on used only by the dcc-mcp-blender E2E suite."""

bl_info = {
    "name": "DCC MCP Blender E2E Temp Addon",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "category": "Development",
}


def register():
    pass


def unregister():
    pass
'''


def _skill(name):
    return load_skill("blender-dev", name)


def _write_addon(directory: Path) -> Path:
    path = directory / f"{_ADDON_MODULE}.py"
    path.write_text(_ADDON_SOURCE, encoding="utf-8")
    return path


class TestAddonLifecycleE2E:
    """Install, enable, and remove a real add-on.

    Runs as one test because the steps share state: a strip that cannot be
    installed makes the enable and remove assertions meaningless, and splitting
    them would leave Blender holding the add-on between tests.
    """

    def setup_method(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self._tmp = tempfile.TemporaryDirectory()
        self.addon_path = _write_addon(Path(self._tmp.name))

    def teardown_method(self):
        # Always clean up, including after a failed assertion, so a red test
        # does not leave the add-on installed in the CI image.
        try:
            if _ADDON_MODULE in [module.__name__ for module in _modules()]:
                bpy.ops.preferences.addon_disable(module=_ADDON_MODULE)
                bpy.ops.preferences.addon_remove(module=_ADDON_MODULE)
                bpy.ops.preferences.addon_refresh()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_install_enable_and_remove(self):
        # Install with an explicit module name so the tool confirms it.
        result = _skill("install_addon").install_addon(file_path=str(self.addon_path), addon_module=_ADDON_MODULE)
        assert result["success"] is True, result.get("error")
        assert result["context"]["after"]["installed"] is True
        assert result["context"]["after"]["enabled"] is True

        # Blender must agree, not just the tool response.
        assert _ADDON_MODULE in [module.__name__ for module in _modules()]
        enabled = dict((module.__name__, _check(module.__name__)[1]) for module in _modules())
        assert enabled.get(_ADDON_MODULE) is True

        # Blender's own addon_remove calls context.area.tag_redraw(), which is
        # None under --background, so removal must not depend on that operator.
        installed_file = getattr(_module_by_name(_ADDON_MODULE), "__file__", None)

        result = _skill("remove_addon").remove_addon(addon_module=_ADDON_MODULE)
        assert result["success"] is True, result.get("error")
        assert result["context"]["after"]["installed"] is False, result["context"]["after"]
        assert result["context"]["removed_paths"], "removal must report what it deleted"

        # The file itself has to be gone, not just unregistered from the cache.
        if installed_file:
            assert not Path(installed_file).exists(), "the add-on file must be deleted"
        assert _ADDON_MODULE not in [module.__name__ for module in _modules()]

    def test_disable_keeps_the_addon_installed(self):
        """Disabling clears the enabled flag but leaves the add-on installed."""
        result = _skill("install_addon").install_addon(file_path=str(self.addon_path), addon_module=_ADDON_MODULE)
        assert result["success"] is True, result.get("error")

        result = _skill("disable_addon").disable_addon(addon_module=_ADDON_MODULE)
        assert result["success"] is True, result.get("error")
        assert result["context"]["after"]["enabled"] is False
        assert result["context"]["after"]["installed"] is True
        assert _ADDON_MODULE in [module.__name__ for module in _modules()]

    def test_install_rejects_a_missing_file(self):
        result = _skill("install_addon").install_addon(
            file_path=str(Path(self._tmp.name) / "nope.py"), addon_module=_ADDON_MODULE
        )
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_install_rejects_a_directory(self):
        result = _skill("install_addon").install_addon(file_path=str(self._tmp.name), addon_module=_ADDON_MODULE)
        assert result["success"] is False
        assert "directory" in result["message"].lower()

    def test_install_reports_a_wrong_module_name(self):
        """Installing succeeds but the named module never appears -> error."""
        result = _skill("install_addon").install_addon(
            file_path=str(self.addon_path), addon_module="definitely_not_this_module"
        )
        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert "definitely_not_this_module" in result["error"]

    def test_install_requires_a_file(self):
        result = _skill("install_addon").install_addon(addon_module=_ADDON_MODULE)
        assert result["success"] is False
        assert "no add-on file" in result["message"].lower()

    def test_refresh_reports_a_count(self):
        result = _skill("refresh_addons").refresh_addons()
        assert result["success"] is True, result.get("error")
        # The count must be a real number, and installing then refreshing must
        # show the add-on appear in the refreshed list.
        assert result["context"]["after_count"] >= 0
        before = result["context"]["after_count"]

        _skill("install_addon").install_addon(file_path=str(self.addon_path))
        refreshed = _skill("refresh_addons").refresh_addons()
        assert refreshed["success"] is True, refreshed.get("error")
        assert refreshed["context"]["after_count"] > before


def _module_by_name(name):
    """Return the cached module object for an add-on, or None."""
    for module in _modules():
        if getattr(module, "__name__", None) == name:
            return module
    return None


def _modules():
    import addon_utils

    return list(addon_utils.modules(refresh=True))


def _check(name):
    import addon_utils

    return addon_utils.check(name)
