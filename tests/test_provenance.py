"""Regression tests for stale-copy detection in the Blender host.

A user-level extension copy that a host loads ahead of the resolved package used
to win silently: it satisfied its own, older compatibility gate, started an MCP
server, and reported an old version without a single error. These tests pin the
three behaviours that make that impossible -- the origin has to be visible, a
declared root has to be enforced, and an undeclared conflict has to be loud.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ADDON_ENTRY = ROOT / "packaging" / "addon_entry" / "__init__.py"

USER_LEVEL_ROOT = os.path.join("profile", "extensions", "bl_ext", "user_default")


def _fake_module(name, origin, version="0.0.1"):
    """Build a module object that reports a given origin, like a stale copy."""
    module = ModuleType(name)
    module.__version__ = version
    module.__file__ = str(origin)
    module.__path__ = [str(pathlib.Path(origin).parent)]
    return module


def _provenance_env_root():
    """Name of the variable that declares the authoritative package root."""
    from dcc_mcp_blender import _provenance

    return _provenance.ENV_EXPECTED_ROOT


def _write_distribution(root, name="dcc_mcp_blender", version="0.2.4"):
    """Create an importable package directory and return its ``__init__.py``."""
    package = root / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__version__.py").write_text('__version__ = "%s"\n' % version, encoding="utf-8")
    return package / "__init__.py"


# --------------------------------------------------------------------------- #
# Declared root enforcement
# --------------------------------------------------------------------------- #


def test_resolve_expected_root_prefers_the_adapter_variable(monkeypatch):
    from dcc_mcp_blender import _provenance

    monkeypatch.setenv(_provenance.ENV_EXPECTED_ROOT, "/resolve/adapter")
    monkeypatch.setenv(_provenance.ENV_EXPECTED_ROOT_FALLBACK, "/resolve/shared")

    assert _provenance.resolve_expected_root() == "/resolve/adapter"


def test_resolve_expected_root_falls_back_to_the_shared_variable(monkeypatch):
    from dcc_mcp_blender import _provenance

    monkeypatch.delenv(_provenance.ENV_EXPECTED_ROOT, raising=False)
    monkeypatch.setenv(_provenance.ENV_EXPECTED_ROOT_FALLBACK, "/resolve/shared")

    assert _provenance.resolve_expected_root() == "/resolve/shared"


def test_expected_roots_accepts_a_path_separated_list(monkeypatch):
    """A package manager that resolves each dcc-mcp package separately must be expressible."""
    from dcc_mcp_blender import _provenance

    monkeypatch.delenv(_provenance.ENV_EXPECTED_ROOT, raising=False)
    monkeypatch.delenv(_provenance.ENV_EXPECTED_ROOT_FALLBACK, raising=False)
    value = os.pathsep.join(["/resolve/adapter", "/resolve/core"])

    assert _provenance.expected_roots(value) == ("/resolve/adapter", "/resolve/core")
    assert _provenance.is_within_any("/resolve/core/dcc_mcp_core", ("/resolve/adapter", "/resolve/core"))
    assert not _provenance.is_within_any("/stale/dcc_mcp_core", ("/resolve/adapter", "/resolve/core"))


def test_runtime_inside_the_declared_root_passes():
    """The healthy case must stay silent and report ``ok``."""
    import dcc_mcp_blender
    from dcc_mcp_blender import _provenance

    root = os.path.dirname(os.path.dirname(os.path.abspath(dcc_mcp_blender.__file__)))
    report = _provenance.collect_report(names=("dcc_mcp_blender",), expected_root=root)

    assert report.ok
    assert report.shadowed == ()
    assert report.warnings == ()
    assert report.modules[0].expected is True


def test_runtime_outside_the_declared_root_fails_closed(monkeypatch):
    """A stale copy below a declared root must raise, not start a server."""
    from dcc_mcp_blender import _provenance

    stale = _fake_module("dcc_mcp_blender", os.path.join(USER_LEVEL_ROOT, "dcc_mcp_blender", "__init__.py"), "0.2.1")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", stale)

    with pytest.raises(_provenance.PackageProvenanceError) as raised:
        _provenance.require_expected_origin(names=("dcc_mcp_blender",), expected_root="/resolve/site-packages")

    message = str(raised.value)
    assert "0.2.1" in message
    assert USER_LEVEL_ROOT in message
    assert _provenance.ENV_EXPECTED_ROOT in message


def test_declared_root_violation_can_be_downgraded_to_a_warning(monkeypatch):
    """Operators who cannot clean a machine need a non-fatal mode."""
    from dcc_mcp_blender import _provenance

    stale = _fake_module("dcc_mcp_blender", os.path.join(USER_LEVEL_ROOT, "dcc_mcp_blender", "__init__.py"), "0.2.1")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", stale)
    monkeypatch.setenv(_provenance.ENV_STRICT, "0")

    report = _provenance.check_provenance(
        names=("dcc_mcp_blender",),
        expected_root="/resolve/site-packages",
        log=False,
    )

    assert not report.ok
    assert [module.name for module in report.shadowed] == ["dcc_mcp_blender"]
    assert report.strict is False


def test_require_expected_origin_ignores_the_strict_override(monkeypatch):
    """The add-on entry must never accept a wrong runtime because of an env var."""
    from dcc_mcp_blender import _provenance

    stale = _fake_module("dcc_mcp_blender", os.path.join(USER_LEVEL_ROOT, "dcc_mcp_blender", "__init__.py"), "0.2.1")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", stale)
    monkeypatch.setenv(_provenance.ENV_STRICT, "0")

    with pytest.raises(_provenance.PackageProvenanceError):
        _provenance.require_expected_origin(names=("dcc_mcp_blender",), expected_root="/resolve/site-packages")


# --------------------------------------------------------------------------- #
# Undeclared conflicts
# --------------------------------------------------------------------------- #


def test_user_level_copy_shadowing_a_distribution_warns(monkeypatch, tmp_path, caplog):
    """With no root declared the conflict must still be reported loudly."""
    from dcc_mcp_blender import _provenance

    _write_distribution(tmp_path, version="0.2.4")
    stale = _fake_module("dcc_mcp_blender", os.path.join(USER_LEVEL_ROOT, "dcc_mcp_blender", "__init__.py"), "0.2.1")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", stale)

    with caplog.at_level("WARNING"):
        report = _provenance.check_provenance(
            names=("dcc_mcp_blender",),
            sys_path=[str(tmp_path)],
            environ={},
        )

    assert report.ok, "an undeclared conflict is advisory, never a failure"
    assert report.expected_root is None
    assert len(report.warnings) == 1
    assert "0.2.1" in report.warnings[0]
    assert str(tmp_path) in report.warnings[0]
    assert report.warnings[0] in caplog.text


def test_a_clean_resolve_produces_no_warning(tmp_path):
    """No conflict, no noise: the warning path must not fire on a healthy host."""
    from dcc_mcp_blender import _provenance

    origin = _write_distribution(tmp_path, version="0.2.4")
    module = _fake_module("dcc_mcp_blender", origin, "0.2.4")
    sys.modules["_provenance_probe_module"] = module

    report = _provenance.collect_report(
        names=("_provenance_probe_module",),
        sys_path=[str(tmp_path)],
        environ={},
    )

    assert report.warnings == ()


def test_the_advised_root_is_accepted_by_the_gate_that_printed_it(monkeypatch, tmp_path):
    """The remediation printed in the warning must not break a healthy host.

    The warning names a ``sys.path`` entry. Printing the package directory
    instead would be off by one level: feeding that value back through
    :data:`ENV_EXPECTED_ROOT` makes every import sit *below* the declared root,
    so the gate rejects a host that was already correct -- and keeps printing
    the same advice.
    """
    from dcc_mcp_blender import _provenance

    _write_distribution(tmp_path, version="0.2.4")
    stale = _fake_module("dcc_mcp_blender", os.path.join(USER_LEVEL_ROOT, "dcc_mcp_blender", "__init__.py"), "0.2.1")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", stale)

    report = _provenance.check_provenance(
        names=("dcc_mcp_blender",),
        sys_path=[str(tmp_path)],
        environ={},
        log=False,
    )
    assert len(report.warnings) == 1
    marker = _provenance.ENV_EXPECTED_ROOT + "="
    assert marker in report.warnings[0]
    advised = report.warnings[0].split(marker, 1)[1].split(" ", 1)[0].strip()

    # The advice names the sys.path entry, never the package directory itself.
    assert os.path.basename(advised) != "dcc_mcp_blender"
    assert os.path.realpath(advised) == os.path.realpath(str(tmp_path))

    # Following the advice must clear the very conflict it was printed for.
    healthy = _fake_module("dcc_mcp_blender", _write_distribution(tmp_path, version="0.2.4"), "0.2.4")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", healthy)
    enforced = _provenance.require_expected_origin(names=("dcc_mcp_blender",), expected_root=advised)
    assert enforced.ok
    assert enforced.shadowed == ()


def test_a_declared_root_spelled_as_the_package_directory_is_accepted(monkeypatch, tmp_path):
    """A root copied from either spelling must be honoured, not rejected."""
    from dcc_mcp_blender import _provenance

    origin = _write_distribution(tmp_path, version="0.2.4")
    module = _fake_module("dcc_mcp_blender", origin, "0.2.4")
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", module)

    package_dir = _provenance.require_expected_origin(
        names=("dcc_mcp_blender",),
        expected_root=str(tmp_path / "dcc_mcp_blender"),
    )
    sys_path_entry = _provenance.require_expected_origin(names=("dcc_mcp_blender",), expected_root=str(tmp_path))

    assert package_dir.ok
    assert sys_path_entry.ok
    assert _provenance.sys_path_entry(str(tmp_path / "dcc_mcp_blender")) == os.path.abspath(str(tmp_path))


def test_user_level_markers_are_matched_on_path_segments():
    from dcc_mcp_blender import _provenance

    assert _provenance.is_user_level(os.path.join("profile", "bl_ext", "user_default"))
    assert _provenance.is_user_level(os.path.join("profile", "scripts", "addons", "dcc_mcp_blender"))
    assert not _provenance.is_user_level(os.path.join("resolve", "site-packages"))


def test_version_tuple_orders_release_versions():
    from dcc_mcp_blender import _provenance

    assert _provenance.version_tuple("0.20.5") > _provenance.version_tuple("0.19.59")
    assert _provenance.version_tuple("0.2.4") >= _provenance.version_tuple("0.2.4")
    assert _provenance.version_tuple("0.20") == (0, 20, 0)


def test_version_tuple_never_ranks_a_pre_release_above_its_release():
    """A pre-release or local suffix must not outrank the release it precedes.

    Keeping the digits of the suffix turned ``1.0.0-rc1`` into ``(1, 0, 1)``,
    which made a release candidate look newer than the release -- and, in the
    hand-over decision, made an older resolve win over the newer extension.
    """
    from dcc_mcp_blender import _provenance

    assert _provenance.version_tuple("1.0.0-rc1") == (1, 0, 0)
    assert _provenance.version_tuple("1.0.0rc1") == (1, 0, 0)
    assert _provenance.version_tuple("0.2.9-rc1") == (0, 2, 9)
    assert _provenance.version_tuple("0.2.10+build5") == (0, 2, 10)
    assert not _provenance.version_tuple("1.0.0-rc1") > _provenance.version_tuple("1.0.0")
    assert _provenance.version_tuple("0.2.9-rc1") < _provenance.version_tuple("0.2.10")


# --------------------------------------------------------------------------- #
# Extension import bridge
# --------------------------------------------------------------------------- #


def _load_addon_entry(monkeypatch, extension_name):
    """Load the add-on entry module under an extension namespace."""
    source_root = ROOT / "src" / "dcc_mcp_blender"
    registered = []
    fake_bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object, Menu=object),
        utils=SimpleNamespace(register_class=registered.append, unregister_class=registered.remove),
    )
    for package in ("bl_ext", "bl_ext.user_default"):
        module = ModuleType(package)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, package, module)
    for name in tuple(sys.modules):
        if name == "dcc_mcp_blender" or name.startswith("dcc_mcp_blender."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    spec = importlib.util.spec_from_file_location(
        extension_name,
        ADDON_ENTRY,
        submodule_search_locations=[str(source_root)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, extension_name, module)
    spec.loader.exec_module(module)
    return module


def test_bridge_origin_lookup_ignores_the_extension_bridge(monkeypatch, tmp_path):
    """A host that loaded the extension copy must still be able to find the real one."""
    from dcc_mcp_blender import _extension_imports

    # Stand in for the extension namespace package and for the distribution the
    # package manager resolved on sys.path (here: the working copy under src/).
    _write_distribution(tmp_path, name="probe_ext", version="0.2.4")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in tuple(sys.modules):
        if name == "probe_ext" or name.startswith("probe_ext."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.delitem(sys.modules, "dcc_mcp_blender")
    bridge = _extension_imports.install_extension_import_aliases("probe_ext", "dcc_mcp_blender")

    try:
        assert sys.meta_path[0] is bridge
        # The facade is what every import gets once the bridge is installed: it
        # hides the resolved distribution completely, which is exactly how a
        # stale extension copy used to win without a single error.
        assert importlib.import_module("dcc_mcp_blender")._dcc_mcp_alias_target.__name__ == "probe_ext"
        # The path-based origin stays visible behind the bridge, so the runtime
        # can still tell that a real distribution was shadowed.
        origin = _extension_imports.public_package_origin("dcc_mcp_blender")
        assert origin is not None
        assert str(tmp_path) not in origin
        assert origin.endswith(os.path.join("dcc_mcp_blender", "__init__.py"))
    finally:
        bridge.uninstall()
        monkeypatch.delitem(sys.modules, "dcc_mcp_blender", raising=False)


def test_public_package_origin_uses_the_injected_meta_path(monkeypatch, tmp_path):
    """The ``meta_path`` argument must be honoured, not silently discarded."""
    from importlib.machinery import PathFinder

    from dcc_mcp_blender import _extension_imports

    _write_distribution(tmp_path, name="probe_injected", version="0.2.4")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in tuple(sys.modules):
        if name == "probe_injected" or name.startswith("probe_injected."):
            monkeypatch.delitem(sys.modules, name)

    # An injected chain is authoritative: without the path finder it sees
    # nothing, and with it the package resolves to the copy on sys.path.
    assert _extension_imports.public_package_origin("probe_injected", meta_path=[]) is None
    origin = _extension_imports.public_package_origin("probe_injected", meta_path=[PathFinder])
    assert origin is not None
    assert os.path.realpath(origin) == os.path.realpath(str(tmp_path / "probe_injected" / "__init__.py"))


def test_canonical_package_hands_over_to_a_newer_resolve(monkeypatch, tmp_path, capsys):
    """The reported case: a stale 0.2.1 extension copy, a resolved 0.2.4 package."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_handover"
    module = _load_addon_entry(monkeypatch, extension_name)
    _write_distribution(tmp_path, version="0.2.4")
    monkeypatch.syspath_prepend(str(tmp_path))

    # The copy on disk is older than the resolve, not the entry point's release.
    stale = tmp_path / "stale-extension"
    _write_distribution(stale, version="0.2.1")
    monkeypatch.setattr(module, "_own_package_dir", lambda: str(stale / "dcc_mcp_blender"))

    assert module._resolve_canonical_package() == "dcc_mcp_blender"
    served = capsys.readouterr().out
    assert "0.2.4" in served
    assert "0.2.1" in served
    # The runtime must then serve the resolved copy, not the stale one.
    assert module._addon_module("__version__").__version__ == "0.2.4"


def test_canonical_package_keeps_control_when_the_extension_is_newer(monkeypatch, tmp_path):
    """A resolve older than the extension copy must not silently downgrade it."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_newer_ext"
    module = _load_addon_entry(monkeypatch, extension_name)
    _write_distribution(tmp_path, version="0.2.4")
    monkeypatch.syspath_prepend(str(tmp_path))

    newer = tmp_path / "newer-extension"
    _write_distribution(newer, version="0.2.10")
    monkeypatch.setattr(module, "_own_package_dir", lambda: str(newer / "dcc_mcp_blender"))

    assert module._resolve_canonical_package() == extension_name


def test_canonical_package_keeps_control_when_the_distribution_is_older(monkeypatch, tmp_path, capsys):
    """Handing over to an older copy would reintroduce the silent downgrade."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_older"
    module = _load_addon_entry(monkeypatch, extension_name)
    _write_distribution(tmp_path, version="0.1.0")
    monkeypatch.syspath_prepend(str(tmp_path))

    current = tmp_path / "current-extension"
    _write_distribution(current, version="0.2.10")
    monkeypatch.setattr(module, "_own_package_dir", lambda: str(current / "dcc_mcp_blender"))

    assert module._resolve_canonical_package() == extension_name
    assert "WARNING" in capsys.readouterr().out


def test_canonical_package_ignores_the_extension_own_source_tree(monkeypatch):
    """A ZIP install whose ``sys.path`` entry is the same tree must not hand over."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_same"
    module = _load_addon_entry(monkeypatch, extension_name)

    assert module._resolve_canonical_package() == extension_name


def test_a_violated_declared_root_does_not_break_the_package_import():
    """Import must report the conflict, never raise: the CLI is the repair path.

    ``dcc-mcp-blender install`` / ``upgrade`` and the ``dcc_mcp.adapters`` entry
    point both import this package. Raising from the package body would kill the
    commands an operator needs to fix the host, and would fire *before* the
    add-on entry and the startup hook can print their clearer diagnosis. It also
    fires on every import when only the adapter root is declared and a package
    manager resolves core elsewhere, which is documented as expected usage.
    """
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    env[_provenance_env_root()] = os.path.join("resolve", "site-packages")

    script = (
        "import dcc_mcp_blender\n"
        "import dcc_mcp_blender.install as install\n"
        "report = dcc_mcp_blender.IMPORT_PROVENANCE_REPORT\n"
        "assert callable(install.main), 'the CLI entry point must stay importable'\n"
        "assert report is not None and not report.ok, 'the conflict must still be reported'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_register_runs_the_core_version_self_check(monkeypatch):
    """``register()`` must refuse to load on a core below the adapter contract."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_gate"
    module = _load_addon_entry(monkeypatch, extension_name)
    original_addon_module = module._addon_module

    def addon_module(name):
        if name == "_core_compat":

            def reject_core():
                raise RuntimeError("requires dcc-mcp-core>=0.20.0, but Blender preloaded 0.19.59")

            return SimpleNamespace(require_compatible_core=reject_core)
        if name == "_provenance":
            return original_addon_module(name)
        return original_addon_module(name)

    monkeypatch.setattr(module, "_addon_module", addon_module)

    with pytest.raises(RuntimeError, match="preloaded 0.19.59"):
        module.register()


def test_canonical_package_ignores_a_pre_release_suffix_when_comparing(monkeypatch, tmp_path):
    """A resolved ``0.2.9-rc1`` must not outrank the ``0.2.10`` copy on disk."""
    extension_name = "bl_ext.user_default.dcc_mcp_blender_pre_release"
    module = _load_addon_entry(monkeypatch, extension_name)
    _write_distribution(tmp_path, version="0.2.9-rc1")
    monkeypatch.syspath_prepend(str(tmp_path))

    current = tmp_path / "current-extension"
    _write_distribution(current, version="0.2.10")
    monkeypatch.setattr(module, "_own_package_dir", lambda: str(current / "dcc_mcp_blender"))

    assert module._resolve_canonical_package() == extension_name


def test_register_gates_the_copy_that_will_actually_serve(monkeypatch, tmp_path):
    """When the extension keeps control, the declared root must cover *it*.

    The public ``dcc_mcp_blender`` name is only bridged onto the extension
    later, so gating that name here would inspect whatever distribution sits on
    ``sys.path`` -- or skip the check entirely when there is none -- and let the
    extension copy serve from outside a declared root unexamined.
    """
    from dcc_mcp_blender import _provenance

    extension_name = "bl_ext.user_default.dcc_mcp_blender_keeps_control"
    module = _load_addon_entry(monkeypatch, extension_name)
    _write_distribution(tmp_path, version="0.2.4")
    monkeypatch.syspath_prepend(str(tmp_path))
    newer = tmp_path / "newer-extension"
    _write_distribution(newer, version="0.2.10")
    monkeypatch.setattr(module, "_own_package_dir", lambda: str(newer / "dcc_mcp_blender"))
    monkeypatch.setenv(_provenance.ENV_EXPECTED_ROOT, str(tmp_path / "resolve"))

    assert module._resolve_canonical_package() == extension_name

    seen = {}
    original_addon_module = module._addon_module

    def addon_module(name):
        if name == "_core_compat":
            return SimpleNamespace(require_compatible_core=lambda: None)
        if name == "_provenance":

            def require_expected_origin(**kwargs):
                seen.update(kwargs)
                raise _provenance.PackageProvenanceError("gated")

            return SimpleNamespace(require_expected_origin=require_expected_origin)
        return original_addon_module(name)

    monkeypatch.setattr(module, "_addon_module", addon_module)

    with pytest.raises(_provenance.PackageProvenanceError):
        module.register()

    assert seen["names"] == (extension_name, "dcc_mcp_core")


def test_register_rejects_a_runtime_outside_the_declared_root(monkeypatch, tmp_path):
    """A declared root is enforced before any operator class is registered."""
    from dcc_mcp_blender import _provenance

    extension_name = "bl_ext.user_default.dcc_mcp_blender_root"
    module = _load_addon_entry(monkeypatch, extension_name)
    monkeypatch.setenv(_provenance.ENV_EXPECTED_ROOT, str(tmp_path / "resolve"))

    # The check raises through the add-on's own package namespace, so the class
    # identity differs from the one imported here: assert on the contract.
    with pytest.raises(Exception) as raised:
        module.register()

    assert type(raised.value).__name__ == "PackageProvenanceError"
    assert "resolved outside the expected package root" in str(raised.value)
