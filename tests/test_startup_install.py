"""Regression tests for Blender startup and read-only install fallbacks."""

from __future__ import annotations

import builtins
import importlib.util
import pathlib
import sys
from types import ModuleType, SimpleNamespace

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
