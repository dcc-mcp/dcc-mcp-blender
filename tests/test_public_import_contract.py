"""Regression tests for the cross-channel ``dcc_mcp_blender`` import contract.

Two distributions ship the same adapter and must expose the same top-level
names:

* the wheel / site-packages channel, where ``dcc_mcp_blender/__init__.py`` is
  the library package init;
* the Blender 4.2+ extension channel, where the add-on package root *is*
  ``dcc_mcp_blender`` and its ``__init__.py`` is the Blender add-on entrypoint.

A pipeline script written as ``dcc_mcp_blender.start_server(...)`` must resolve
identically in both, and must keep resolving after
``bpy.ops.wm.read_factory_settings(use_empty=True)`` — the standard "open a
clean scene" prologue that makes Blender disable every add-on.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import pathlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ADDON_ENTRY = ROOT / "packaging" / "addon_entry" / "__init__.py"
SRC_ROOT = ROOT / "src" / "dcc_mcp_blender"
PUBLIC_API = SRC_ROOT / "_public_api.py"

EXTENSION_NAME = "bl_ext.user_default.dcc_mcp_blender"


def _library_public_names() -> set[str]:
    """Read the canonical public surface without importing either channel."""
    tree = ast.parse(PUBLIC_API.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"could not find __all__ in {PUBLIC_API}")


def _purge_public_modules(monkeypatch) -> None:
    for name in tuple(sys.modules):
        if name == "dcc_mcp_blender" or name.startswith("dcc_mcp_blender."):
            monkeypatch.delitem(sys.modules, name)


def _purge_public_modules_for_reimport(addon_module) -> None:
    """Drop cached public facades so the next import rebuilds them."""
    aliases = addon_module._runtime_import_aliases
    if aliases is not None:
        aliases.detach()
    for name in tuple(sys.modules):
        if name == "dcc_mcp_blender" or name.startswith("dcc_mcp_blender."):
            del sys.modules[name]


def _register_ext_namespace(monkeypatch) -> None:
    for package in ("bl_ext", "bl_ext.user_default"):
        module = ModuleType(package)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, package, module)


def _load_addon_entry(monkeypatch, name: str = EXTENSION_NAME):
    fake_bpy = SimpleNamespace(types=SimpleNamespace(Operator=object, Menu=object))
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    spec = importlib.util.spec_from_file_location(
        name,
        ADDON_ENTRY,
        submodule_search_locations=[str(SRC_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def extension_addon(monkeypatch):
    """Load the add-on entrypoint the way Blender loads an extension."""
    _purge_public_modules(monkeypatch)
    _register_ext_namespace(monkeypatch)
    module = _load_addon_entry(monkeypatch)
    yield module
    # Leave no finder behind for other tests.
    for finder in list(sys.meta_path):
        if getattr(finder, "canonical_package", None) == EXTENSION_NAME:
            finder.uninstall()
    _purge_public_modules(monkeypatch)


def test_wheel_channel_publishes_the_library_surface():
    """``dcc_mcp_blender.__all__`` must be exactly the canonical surface."""
    import dcc_mcp_blender as public

    assert set(public.__all__) == _library_public_names()


def test_wheel_and_extension_channels_expose_the_same_top_level_names(extension_addon):
    """Every public name must resolve in the extension channel too."""
    library_names = _library_public_names()
    assert {"BlenderHost", "start_server", "build_manifest_payload"} <= library_names

    extension_addon._install_runtime_import_aliases()
    extension_public = importlib.import_module("dcc_mcp_blender")

    missing = sorted(name for name in library_names if not hasattr(extension_public, name))
    assert not missing, f"extension channel is missing top-level names: {missing}"
    assert set(extension_public.__all__) >= library_names


def test_both_channels_return_the_same_version_value(extension_addon):
    """``__version__`` must be the version string in the extension channel too.

    Importing the ``__version__`` submodule binds the module object as the
    package attribute; left alone, the extension channel would answer with a
    module where the wheel channel answers with a string.
    """
    import dcc_mcp_blender as wheel_public

    wheel_version = wheel_public.__version__

    _purge_public_modules_for_reimport(extension_addon)
    extension_addon._install_runtime_import_aliases()
    extension_public = importlib.import_module("dcc_mcp_blender")

    assert isinstance(wheel_version, str)
    assert extension_public.__version__ == wheel_version
    assert isinstance(extension_public.__version__, str)


def test_extension_channel_resolves_real_callables(extension_addon):
    """Aliased attributes must be the same objects the add-on itself uses."""
    extension_addon._install_runtime_import_aliases()
    public = importlib.import_module("dcc_mcp_blender")
    server = extension_addon._addon_module("server")
    host = extension_addon._addon_module("host")

    assert public.start_server is server.start_server
    assert public.stop_server is server.stop_server
    assert public.get_server is server.get_server
    assert public.BlenderHost is host.BlenderHost
    assert public.BlenderUiDispatcher is host.BlenderUiDispatcher


def test_factory_reset_keeps_public_import_resolvable(extension_addon):
    """``read_factory_settings`` disables add-ons but must not break imports."""
    extension_addon._install_runtime_import_aliases()
    assert importlib.import_module("dcc_mcp_blender").start_server is not None

    # Blender disables every add-on on a factory reset: unregister() runs.
    extension_addon.unregister()

    public = importlib.import_module("dcc_mcp_blender")
    assert public.start_server is not None
    assert importlib.import_module("dcc_mcp_blender.server").get_server is not None


def test_public_import_survives_purged_extension_namespace(extension_addon, monkeypatch):
    """A script reload that purges ``bl_ext.*`` must still resolve imports."""
    extension_addon._install_runtime_import_aliases()
    first = importlib.import_module("dcc_mcp_blender")

    # Blender's script reload drops the extension namespace from sys.modules.
    for name in tuple(sys.modules):
        if name.startswith("bl_ext"):
            monkeypatch.delitem(sys.modules, name)
    _purge_public_modules(monkeypatch)

    public = importlib.import_module("dcc_mcp_blender")
    assert public is not first
    assert public.start_server is not None
    assert importlib.import_module("dcc_mcp_blender.host").BlenderHost is not None


def test_failed_enable_still_withdraws_the_bridge(extension_addon, monkeypatch):
    """A failed enable must not leave the public contract half-installed."""
    original = extension_addon._addon_module

    def addon_module(name):
        if name == "_core_compat":

            def reject_core():
                raise RuntimeError("incompatible core")

            return SimpleNamespace(require_compatible_core=reject_core)
        return original(name)

    monkeypatch.setattr(extension_addon, "_addon_module", addon_module)
    monkeypatch.delenv("DCC_MCP_UI_CONTROL_PROCESS_ID", raising=False)

    with pytest.raises(RuntimeError, match="incompatible core"):
        extension_addon._start_server_with_host()

    assert extension_addon._runtime_import_aliases is None
    assert not any(getattr(finder, "canonical_package", None) == EXTENSION_NAME for finder in sys.meta_path)
    assert not any(name == "dcc_mcp_blender" or name.startswith("dcc_mcp_blender.") for name in sys.modules)


def test_addon_entry_does_not_eagerly_import_the_adapter(extension_addon, monkeypatch):
    """Blender imports add-ons just to read ``bl_info``; keep that cheap."""
    imported = []
    original = extension_addon._addon_module

    def spy(name):
        imported.append(name)
        return original(name)

    monkeypatch.setattr(extension_addon, "_addon_module", spy)

    assert extension_addon.BlenderHost is not None

    # ``_isolated_path`` repairs PYTHONPATH on hosts that boot an isolated
    # Python (Blender 5.x) and must run before the public surface binds core.
    assert imported == ["_isolated_path", "_public_api"]


def _install_gate_spies(monkeypatch, package: str) -> list[str]:
    """Substitute recording stubs for the gate modules of ``package``.

    The stubs must be installed *before* ``_public_api`` is imported, because
    it binds the gates with ``from ._x import y`` at import time. What gets
    recorded is therefore what the channel really executed -- not what its
    source looks like.
    """
    calls: list[str] = []

    def recorder(name: str):
        def gate(*args, **kwargs):
            calls.append(name)
            return [] if name == "repair_sys_path" else {}

        return gate

    for submodule in ("__version__", "_isolated_path", "_host_support", "_core_compat"):
        stub = ModuleType(f"{package}.{submodule}")
        stub.__version__ = "0.2.10"
        for gate_name in ("repair_sys_path", "require_supported_host", "require_compatible_core"):
            setattr(stub, gate_name, recorder(gate_name))
        monkeypatch.setitem(sys.modules, f"{package}.{submodule}", stub)
    return calls


def _assert_gates_ran_in_order(calls: list[str]) -> None:
    """Assert every declared gate ran, and in the declared order.

    Presence alone is not enough: ``require_supported_host`` before
    ``repair_sys_path`` would turn every Blender 5.x host into a hard
    ``HostSupportError`` even on hosts the repair rescues.
    """
    from dcc_mcp_blender._public_api import PUBLIC_API_GATE_NAMES

    for name in PUBLIC_API_GATE_NAMES:
        assert name in calls, f"gate {name!r} never ran; the channel executed {calls}"
    # Judge only the import prologue, ending at the last gate. Code that runs
    # later (the advisory provenance check) re-imports these modules and would
    # otherwise add trailing calls that have nothing to do with gate order.
    final_gate = PUBLIC_API_GATE_NAMES[-1]
    prologue = calls[: calls.index(final_gate) + 1]
    # A gate may legitimately run more than once inside the prologue -- the
    # add-on entry repairs the path before it imports the surface, which
    # repairs it again. Compare the *last* run of each gate so an extra repair
    # cannot mask an out-of-order one.
    last_run = {name: max(i for i, seen in enumerate(prologue) if seen == name) for name in PUBLIC_API_GATE_NAMES}
    order = [last_run[name] for name in PUBLIC_API_GATE_NAMES]
    assert order == sorted(order), f"gates ran out of order: {calls}"


def test_wheel_channel_runs_every_import_gate_in_order(monkeypatch):
    """The wheel channel must run all three gates, repair first.

    The host gate used to live inline in ``src/dcc_mcp_blender/__init__.py``.
    Moving the surface into ``_public_api`` dropped it there, and with it the
    named ``HostSupportError`` boundary -- silently, because the exported names
    were all still present.
    """
    _purge_public_modules(monkeypatch)
    calls = _install_gate_spies(monkeypatch, "dcc_mcp_blender")

    importlib.import_module("dcc_mcp_blender._public_api")

    _assert_gates_ran_in_order(calls)


def test_extension_channel_runs_every_import_gate_in_order(extension_addon, monkeypatch):
    """The extension channel must run the same gates as the wheel channel.

    Both channels import the same ``_public_api`` module under different
    package namespaces; this is the guard that keeps a gate added to only one
    of them from quietly vanishing from the other.
    """
    # Earlier tests already imported the surface under this namespace; drop it
    # so the stubs below are the gates it actually binds.
    for name in tuple(sys.modules):
        if name.startswith(f"{EXTENSION_NAME}."):
            monkeypatch.delitem(sys.modules, name)
    calls = _install_gate_spies(monkeypatch, EXTENSION_NAME)

    extension_addon._public_api_module()

    _assert_gates_ran_in_order(calls)


def test_addon_entry_dunder_exports_match_the_library_surface(extension_addon):
    """``_DUNDER_EXPORTS`` must track every underscore-prefixed public name."""
    expected = {name for name in _library_public_names() if name.startswith("__")}

    assert set(extension_addon._DUNDER_EXPORTS) == expected


def test_submodule_imports_do_not_recurse_into_the_public_api(extension_addon):
    """``from . import _capability_manifest`` must reach the real submodule.

    Bundled adapter modules import private siblings this way. If the package
    ``__getattr__`` answers the lookup (or tries to resolve it through
    ``_public_api``), the import machinery never loads the submodule and the
    whole package becomes unimportable.
    """
    server = extension_addon._addon_module("server")
    snapshot = extension_addon._addon_module("context_snapshot")

    assert server.__name__ == f"{EXTENSION_NAME}.server"
    assert snapshot.__name__ == f"{EXTENSION_NAME}.context_snapshot"

    with pytest.raises(AttributeError):
        extension_addon._capability_manifest  # noqa: B018 - before submodule import

    capability = extension_addon._addon_module("_capability_manifest")
    assert capability.__name__ == f"{EXTENSION_NAME}._capability_manifest"
