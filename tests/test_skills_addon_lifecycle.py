"""Unit tests for the add-on lifecycle tools (bpy mocked)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import yaml

from tests.conftest import load_and_call, make_mock_bpy

DEV_PATH = "src/dcc_mcp_blender/skills/blender-dev/tools.yaml"
SKILL = "blender-dev"


class _FakeOps:
    """Records preference operator calls, mutates state, and can fail on demand.

    Enable and disable actually change the enabled map, so the tools' own
    post-condition checks behave the way they do against Blender rather than
    passing on a mock that never changes.
    """

    def __init__(self, fail=(), installed=()):
        self.calls: list = []
        self.removed: list = []
        self._fail = set(fail)
        _ENABLED.clear()
        for name in installed:
            _ENABLED[name] = False

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name in self._fail:
            raise RuntimeError(f"{name} failed")
        module = kwargs.get("module")
        if name == "addon_enable" and module is not None:
            _ENABLED[module] = True
        if name == "addon_disable" and module is not None:
            _ENABLED[module] = False
        if name == "addon_remove" and module is not None:
            self.removed.append(module)
            _ENABLED.pop(module, None)
        return {"FINISHED"}

    def __getattr__(self, name):
        def _call(**kwargs):
            return self._record(name, **kwargs)

        return _call


def _bpy_with_addons(modules, ops=None):
    """Build a bpy mock whose add-on list behaves like Blender's cache.

    `_addon_modules()` calls addon_utils.modules(refresh=False), so the list
    keeps returning stale entries until a refresh runs. The mock drops removed
    modules only on refresh, which is what makes the post-condition checks in
    install_addon and remove_addon meaningful.
    """
    bpy = make_mock_bpy()
    # Always own the ops object so the cached module list can consult it; the
    # caller may pass one in to inspect the recorded calls.
    ops_ref = ops if ops is not None else _FakeOps()
    bpy.ops.preferences = ops_ref
    bpy.data.objects = []

    state = {"modules": list(modules)}

    def _modules(refresh=False):
        if refresh:
            # addon_remove only takes effect in the cached list after a refresh.
            state["modules"] = [m for m in state["modules"] if m.__name__ not in ops_ref.removed]
        return list(state["modules"])

    def _check(name: str):
        current = {getattr(m, "__name__", "") for m in state["modules"]}
        if name not in current:
            return (False, False)
        return (True, _ENABLED.get(name, False))

    addon_utils = SimpleNamespace(
        modules=_modules,
        check=_check,
        module_bl_info=lambda module: {"name": getattr(module, "__name__", "").upper()},
    )
    _patch_addon_utils(bpy, addon_utils)
    return bpy


def _make_check(known):
    """Mirror addon_utils.check: (loaded, enabled) for known modules only."""

    def _check(name: str):
        if name not in known:
            return (False, False)
        return (True, _ENABLED.get(name, False))

    return _check


def _patch_addon_utils(bpy, addon_utils):
    """Register a fake addon_utils in sys.modules for the duration of a call."""
    import sys

    sys.modules["addon_utils"] = addon_utils


_ENABLED: dict = {}


def _module(name: str):
    return SimpleNamespace(__name__=name)


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL}/scripts/{script}.py", bpy, **kwargs)


def setup_function():
    _ENABLED.clear()


def _make_addon_file(tmp_path: Path, name: str = "my_addon.py") -> Path:
    path = tmp_path / name
    path.write_text("bl_info = {'name': 'My Addon', 'version': (1, 0, 0)}\n", encoding="utf-8")
    return path


def _make_zip(tmp_path: Path, name: str = "my_addon.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("my_addon/__init__.py", "bl_info = {'name': 'My Addon'}\n")
    return path


# ---------------------------------------------------------------------------
# install_addon
# ---------------------------------------------------------------------------


def test_install_addon_installs_and_enables(tmp_path):
    path = _make_addon_file(tmp_path)
    modules = [_module("my_addon")]
    ops = _FakeOps()
    bpy = _bpy_with_addons(modules, ops)

    result = _call("install_addon", bpy, file_path=str(path), addon_module="my_addon")

    assert result["success"] is True, result.get("error")
    names = [name for name, _ in ops.calls]
    assert "addon_install" in names
    # Installing leaves the module cache stale, so a refresh has to follow.
    assert "addon_refresh" in names
    assert "addon_enable" in names


def test_install_addon_rejects_a_missing_file(tmp_path):
    result = _call("install_addon", _bpy_with_addons([]), file_path=str(tmp_path / "nope.py"))
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_install_addon_rejects_an_unsupported_extension(tmp_path):
    path = tmp_path / "addon.tar.gz"
    path.write_text("x", encoding="utf-8")
    result = _call("install_addon", _bpy_with_addons([]), file_path=str(path))
    assert result["success"] is False
    assert "unsupported add-on file" in result["message"].lower()


def test_install_addon_rejects_a_directory(tmp_path):
    result = _call("install_addon", _bpy_with_addons([]), file_path=str(tmp_path))
    assert result["success"] is False
    assert "directory" in result["message"].lower()


def test_install_addon_reports_a_wrong_module_name(tmp_path):
    """Installing a zip whose package name differs must not silently succeed."""
    path = _make_zip(tmp_path)
    bpy = _bpy_with_addons([])  # module never appears

    result = _call("install_addon", bpy, file_path=str(path), addon_module="definitely_not_this")
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_install_addon_reports_operator_failure(tmp_path):
    path = _make_addon_file(tmp_path)
    ops = _FakeOps(fail=["addon_install"])
    result = _call("install_addon", _bpy_with_addons([], ops), file_path=str(path), addon_module="my_addon")

    assert result["success"] is False
    assert "failed to install" in result["message"].lower()


def test_install_addon_can_skip_enabling(tmp_path):
    path = _make_addon_file(tmp_path)
    ops = _FakeOps()
    bpy = _bpy_with_addons([_module("my_addon")], ops)

    result = _call("install_addon", bpy, file_path=str(path), addon_module="my_addon", enable=False)
    assert result["success"] is True
    assert "addon_enable" not in [name for name, _ in ops.calls]


def test_install_addon_requires_a_file():
    """There is nothing to install from without a source, and addon_install("")
    would just fail inside Blender."""
    result = _call("install_addon", _bpy_with_addons([]), addon_module="my_addon")
    assert result["success"] is False
    assert "no add-on file" in result["message"].lower()
    assert "refresh_addons" in result["error"]


def test_install_addon_without_a_module_still_installs(tmp_path):
    """Installing without addon_module installs but cannot confirm the module."""
    path = _make_addon_file(tmp_path)
    ops = _FakeOps()
    bpy = _bpy_with_addons([_module("my_addon")], ops)

    result = _call("install_addon", bpy, file_path=str(path))
    assert result["success"] is True, result.get("error")
    assert result["context"]["module"] is None
    assert result["context"]["enabled"] is False
    assert "addon_enable" not in [name for name, _ in ops.calls], "nothing to enable without a module"
    assert "addon_refresh" in [name for name, _ in ops.calls]


# ---------------------------------------------------------------------------
# remove_addon
# ---------------------------------------------------------------------------


def test_remove_addon_disables_then_removes():
    # _FakeOps clears the enabled map on construction, so enable it afterwards.
    ops = _FakeOps(installed=["my_addon"])
    _ENABLED["my_addon"] = True
    bpy = _bpy_with_addons([_module("my_addon")], ops)
    result = _call("remove_addon", bpy, addon_module="my_addon")

    assert result["success"] is True
    names = [name for name, _ in ops.calls]
    assert names == ["addon_disable", "addon_remove", "addon_refresh"]
    # The cached module list would otherwise still report it as installed.
    assert result["context"]["after"]["installed"] is False


def test_remove_addon_skips_disable_when_already_disabled():
    ops = _FakeOps()
    result = _call("remove_addon", _bpy_with_addons([_module("my_addon")], ops), addon_module="my_addon")

    assert result["success"] is True
    names = [name for name, _ in ops.calls]
    assert names == ["addon_remove", "addon_refresh"]


def test_remove_addon_reports_operator_failure():
    ops = _FakeOps(fail=["addon_remove"])
    result = _call("remove_addon", _bpy_with_addons([_module("my_addon")], ops), addon_module="my_addon")

    assert result["success"] is False
    assert "failed to remove" in result["message"].lower()


# ---------------------------------------------------------------------------
# refresh_addons
# ---------------------------------------------------------------------------


def test_refresh_addons_reports_the_count_delta():
    modules = [_module("a")]
    bpy = make_mock_bpy()
    ops = _FakeOps()
    bpy.ops.preferences = ops

    counter = {"n": 0}

    def _modules(refresh=False):
        counter["n"] += 1
        # First call is the "before" snapshot; simulate one add-on appearing.
        return list(modules) if counter["n"] == 1 else list(modules) + [_module("b")]

    _patch_addon_utils(bpy, SimpleNamespace(modules=_modules, check=lambda n: (False, False)))

    result = _call("refresh_addons", bpy)

    assert result["success"] is True
    assert result["context"]["before_count"] == 1
    assert result["context"]["after_count"] == 2
    assert result["context"]["added"] == 1
    assert "addon_refresh" in [name for name, _ in ops.calls]


def test_refresh_addons_reports_operator_failure():
    bpy = make_mock_bpy()
    bpy.ops.preferences = _FakeOps(fail=["addon_refresh"])
    _patch_addon_utils(bpy, SimpleNamespace(modules=lambda refresh=False: [], check=lambda n: (False, False)))

    result = _call("refresh_addons", bpy)
    assert result["success"] is False
    assert "failed to refresh" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_the_new_tools():
    doc = yaml.safe_load(Path(DEV_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {"install_addon", "remove_addon", "refresh_addons"}.issubset(tools)


def test_new_addon_tools_declare_required_contract_fields():
    doc = yaml.safe_load(Path(DEV_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    for name in ("install_addon", "remove_addon", "refresh_addons"):
        tool = tools[name]
        assert tool["execution"] == "sync", name
        assert tool["affinity"] == "main", name
        source = Path("src/dcc_mcp_blender/skills") / SKILL / tool["source_file"]
        assert source.is_file(), f"missing source script: {source}"


def test_remove_addon_is_flagged_destructive():
    doc = yaml.safe_load(Path(DEV_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert tools["remove_addon"]["destructive"] is True
    assert tools["remove_addon"]["annotations"]["destructive_hint"] is True
    assert tools["refresh_addons"]["destructive"] is False
    assert tools["install_addon"]["destructive"] is False
