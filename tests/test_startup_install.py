"""Regression tests for Blender startup and read-only install fallbacks."""

from __future__ import annotations

import builtins
import contextlib
import importlib.util
import pathlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).parent.parent
SETUP_SCRIPT = ROOT / "skills" / "dcc-mcp-blender-setup" / "scripts" / "setup_dcc_mcp_blender.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_dcc_mcp_blender_for_tests", SETUP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_startup_module(path: pathlib.Path, monkeypatch):
    """Import the generated startup script while Blender dependencies are unavailable."""
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "dcc_mcp_blender" or name.startswith("dcc_mcp_blender."):
            raise AssertionError("startup discovery imported dcc_mcp_blender eagerly")
        return real_import(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location("dcc_mcp_blender_startup_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", guarded_import)
        spec.loader.exec_module(module)
    return module


def test_setup_installs_blender5_registerable_idempotent_startup_script(monkeypatch, tmp_path):
    """The real setup entrypoint must install a Blender 5.x registerable script."""
    setup = _load_setup_module()
    blender_python = tmp_path / "Blender 5.2" / "5.2" / "python" / "bin" / "python.exe"
    blender_python.parent.mkdir(parents=True)
    blender_python.touch()
    user_scripts = tmp_path / "user-scripts"

    monkeypatch.setattr(setup, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "resolve_blender_python", lambda _explicit: blender_python)
    monkeypatch.setattr(setup, "install_package", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup, "verify_import", lambda _python: None)
    monkeypatch.setattr(setup, "write_mcp_snippets", lambda *args, **kwargs: None)
    monkeypatch.setenv("BLENDER_USER_SCRIPTS", str(user_scripts))

    assert setup.main([]) == 0

    startup_path = user_scripts / "startup" / "dcc_mcp_blender_startup.py"
    assert startup_path.is_file()
    startup = _load_startup_module(startup_path, monkeypatch)
    assert callable(startup.register)
    assert callable(startup.unregister)

    calls = []
    state = {"server": None}
    running_server = SimpleNamespace(is_running=True)
    fake_package = ModuleType("dcc_mcp_blender")

    def start_server():
        calls.append("start")
        state["server"] = running_server
        return running_server

    def stop_server():
        calls.append("stop")
        state["server"] = None

    fake_package.get_server = lambda: state["server"]
    fake_package.start_server = start_server
    fake_package.stop_server = stop_server
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", fake_package)

    assert startup.register() is running_server
    assert startup.register() is running_server
    assert calls == ["start"]

    startup.unregister()
    startup.unregister()
    assert calls == ["start", "stop"]

    existing_server = SimpleNamespace(is_running=True)
    state["server"] = existing_server
    assert startup.register() is existing_server
    startup.unregister()
    assert calls == ["start", "stop"]
    assert state["server"] is existing_server


def test_user_install_pairs_pip_user_with_blender_system_environment(monkeypatch):
    """The fallback must install to user site and surface Blender's matching launch flag."""
    setup = _load_setup_module()
    args = setup.parse_args(["--user"])
    commands = []
    monkeypatch.setattr(setup, "run", lambda command, cwd=None: commands.append((command, cwd)))

    setup.install_package(
        pathlib.Path("blender-python"),
        "pypi",
        ROOT,
        skip_install=False,
        user_install=args.user_install,
    )

    assert all("--user" in command for command, _cwd in commands)
    assert setup.blender_launch_command("blender", user_install=args.user_install) == [
        "blender",
        "--python-use-system-env",
    ]

    install_guide = (ROOT / "install.md").read_text(encoding="utf-8")
    assert "-m pip install --user" in install_guide
    assert "blender --python-use-system-env" in install_guide


def test_startup_bridge_captures_and_reraises_bootstrap_failures(monkeypatch, tmp_path):
    """Early startup failures must remain visible both to Core and Blender."""
    setup = _load_setup_module()
    blender_python = tmp_path / "Blender 5.2" / "5.2" / "python" / "bin" / "python.exe"
    blender_python.parent.mkdir(parents=True)
    blender_python.touch()
    startup_path = setup.install_startup_script(blender_python, str(tmp_path / "scripts"))
    startup = _load_startup_module(startup_path, monkeypatch)
    captured = []

    @contextlib.contextmanager
    def capture_bootstrap_errors(dcc_name, **kwargs):
        try:
            yield
        except BaseException as exc:
            captured.append((dcc_name, kwargs, exc))
            raise

    fake_core = ModuleType("dcc_mcp_core")
    fake_core.capture_bootstrap_errors = capture_bootstrap_errors
    fake_package = ModuleType("dcc_mcp_blender")
    fake_package.get_server = lambda: (_ for _ in ()).throw(RuntimeError("startup exploded"))
    fake_package.start_server = lambda: None
    monkeypatch.setitem(sys.modules, "dcc_mcp_core", fake_core)
    monkeypatch.setitem(sys.modules, "dcc_mcp_blender", fake_package)

    with pytest.raises(RuntimeError, match="startup exploded"):
        startup.register()

    assert captured[0][0] == "blender"
    assert captured[0][1]["phase"] == "startup"
    assert captured[0][2].args == ("startup exploded",)


def _render_startup(tmp_path, monkeypatch):
    """Render the lifecycle-owned startup script and load it as a module."""
    from dcc_mcp_blender import install as lifecycle

    site_packages = tmp_path / "site-packages"
    context = SimpleNamespace(
        site_packages=site_packages,
        bootstrap_log_dir=tmp_path / "bootstrap-logs",
    )
    script = tmp_path / "dcc_mcp_blender_startup.py"
    script.write_text(lifecycle._render_startup_script(context), encoding="utf-8")
    return _load_startup_module(script, monkeypatch)


def _installed_module(tmp_path, name, version):
    """Build a module that reports an origin inside the installed site-packages."""
    origin = tmp_path / "site-packages" / name / "__init__.py"
    origin.parent.mkdir(parents=True, exist_ok=True)
    origin.write_text("", encoding="utf-8")
    module = ModuleType(name)
    module.__file__ = str(origin)
    module.__version__ = version
    return module


def _stale_module(root, name, version):
    """Build a module that reports an origin inside a user-level extension copy."""
    origin = root / "extensions" / "bl_ext" / "user_default" / name / "__init__.py"
    origin.parent.mkdir(parents=True, exist_ok=True)
    origin.write_text("", encoding="utf-8")
    module = ModuleType(name)
    module.__file__ = str(origin)
    module.__version__ = version
    return module


def test_startup_script_rejects_a_stale_user_level_adapter(monkeypatch, tmp_path):
    """A user-level copy must never answer for the installed package silently."""
    startup = _render_startup(tmp_path, monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_blender",
        _stale_module(tmp_path, "dcc_mcp_blender", "0.2.1"),
    )
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_core",
        _installed_module(tmp_path, "dcc_mcp_core", "0.20.28"),
    )

    with pytest.raises(RuntimeError) as raised:
        startup._assert_expected_origin()

    message = str(raised.value)
    assert "dcc_mcp_blender 0.2.1" in message
    assert "bl_ext" in message


def test_startup_script_accepts_the_installed_origin(monkeypatch, tmp_path):
    """The healthy case must stay silent."""
    startup = _render_startup(tmp_path, monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_blender",
        _installed_module(tmp_path, "dcc_mcp_blender", "0.2.10"),
    )
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_core",
        _installed_module(tmp_path, "dcc_mcp_core", "0.20.28"),
    )

    assert startup._assert_expected_origin() is None


def test_startup_script_treats_a_foreign_core_as_advisory(monkeypatch, tmp_path, capsys):
    """A Core from another interpreter directory is legitimate: version gates it."""
    startup = _render_startup(tmp_path, monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_blender",
        _installed_module(tmp_path, "dcc_mcp_blender", "0.2.10"),
    )
    foreign = ModuleType("dcc_mcp_core")
    foreign.__file__ = str(tmp_path / "other-interpreter" / "site-packages" / "dcc_mcp_core" / "__init__.py")
    foreign.__version__ = "0.20.28"
    monkeypatch.setitem(sys.modules, "dcc_mcp_core", foreign)

    assert startup._assert_expected_origin() is None
    assert "NOTE" in capsys.readouterr().out


def test_startup_script_violation_can_be_downgraded(monkeypatch, tmp_path, capsys):
    """Operators who accept the risk need a documented non-fatal switch."""
    startup = _render_startup(tmp_path, monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_blender",
        _stale_module(tmp_path, "dcc_mcp_blender", "0.2.1"),
    )
    monkeypatch.setenv("DCC_MCP_BLENDER_STRICT_ORIGIN", "0")

    assert startup._assert_expected_origin() is None
    assert "WARNING" in capsys.readouterr().out
