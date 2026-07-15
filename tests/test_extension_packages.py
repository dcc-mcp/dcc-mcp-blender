from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_blender.extension_packages import (
    ExtensionPackageError,
    install_extension_package,
    plan_extension_install,
)


def _extension_zip(path: Path) -> Path:
    manifest = """
schema_version = "1.0.0"
id = "sample_extension"
version = "1.2.3"
name = "Sample Extension"
tagline = "Example"
maintainer = "Example"
type = "add-on"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sample/blender_manifest.toml", manifest)
        archive.writestr("sample/__init__.py", "def register(): pass\n")
    return path


def test_plan_extension_package(tmp_path: Path) -> None:
    archive = _extension_zip(tmp_path / "sample.zip")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    plan = plan_extension_install(
        {
            "package_id": "sample_extension",
            "archive_path": str(archive),
            "sha256": digest,
        }
    )
    assert plan["package_kind"] == "extension"
    assert plan["version"] == "1.2.3"
    assert plan["manifest_path"] == "sample/blender_manifest.toml"


def test_plan_legacy_addon(tmp_path: Path) -> None:
    archive = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("legacy_addon/__init__.py", "bl_info = {'name': 'Legacy'}\n")
    plan = plan_extension_install({"archive_path": str(archive)})
    assert plan["package_kind"] == "legacy_addon"
    assert plan["package_id"] == "legacy_addon"


def test_rejects_unsafe_archive_path(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape/__init__.py", "")
    with pytest.raises(ExtensionPackageError, match="Unsafe archive path"):
        plan_extension_install({"archive_path": str(archive)})


def test_installs_extension_with_blender_operator(tmp_path: Path) -> None:
    archive = _extension_zip(tmp_path / "sample.zip")
    install_operator = MagicMock(return_value={"FINISHED"})
    repo = SimpleNamespace(
        enabled=True,
        source="USER",
        module="user_default",
        directory=str(tmp_path / "extensions"),
        name="User Extensions",
    )
    bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 2, 0)),
        context=SimpleNamespace(preferences=SimpleNamespace(extensions=SimpleNamespace(repos=[repo]))),
        ops=SimpleNamespace(
            extensions=SimpleNamespace(package_install_files=install_operator),
            preferences=SimpleNamespace(),
        ),
    )
    addon_utils = SimpleNamespace(
        modules=MagicMock(
            side_effect=[
                [],
                [SimpleNamespace(__name__="bl_ext.user_default.sample_extension")],
            ]
        ),
        check=MagicMock(return_value=(True, True)),
    )
    with patch.dict(sys.modules, {"bpy": bpy, "addon_utils": addon_utils}):
        result = install_extension_package({"archive_path": str(archive)}, enable=True)
    assert result["addon_modules"] == ["bl_ext.user_default.sample_extension"]
    install_operator.assert_called_once_with(
        "EXEC_DEFAULT",
        filepath=str(archive.resolve()),
        repo="user_default",
        enable_on_install=True,
        overwrite=False,
    )


def test_installs_legacy_addon_with_preferences_operator(tmp_path: Path) -> None:
    archive = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("legacy_addon/__init__.py", "bl_info = {'name': 'Legacy'}\n")
    install_operator = MagicMock(return_value={"FINISHED"})
    enable_operator = MagicMock(return_value={"FINISHED"})
    bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 2, 0)),
        ops=SimpleNamespace(
            preferences=SimpleNamespace(
                addon_install=install_operator,
                addon_enable=enable_operator,
            )
        ),
    )
    addon_utils = SimpleNamespace(
        modules=MagicMock(side_effect=[[], [SimpleNamespace(__name__="legacy_addon")]]),
        check=MagicMock(return_value=(True, True)),
    )
    with patch.dict(sys.modules, {"bpy": bpy, "addon_utils": addon_utils}):
        result = install_extension_package({"archive_path": str(archive)}, enable=True)
    assert result["addon_modules"] == ["legacy_addon"]
    install_operator.assert_called_once_with("EXEC_DEFAULT", filepath=str(archive.resolve()), overwrite=False)
    enable_operator.assert_called_once_with(module="legacy_addon")
