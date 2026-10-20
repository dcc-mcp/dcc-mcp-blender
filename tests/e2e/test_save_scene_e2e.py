"""Real Blender save/reopen acceptance, separate from fault-injection unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="Native Blender required")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


@pytest.fixture
def save_fixture():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.name = "SavedMarker"
    return load_skill("blender-scene", "save_scene").save_scene


def assert_verified(result, expected):
    assert result["success"], result
    assert result["postcondition"]["verified"] is True
    assert result["postcondition"]["method"] == "finished_operator_matching_scene_path_nonempty_file"
    actual = Path(result["context"]["filepath"])
    assert actual.samefile(expected)
    assert result["context"]["file_size_bytes"] == actual.stat().st_size > 0
    assert result["context"]["operator_result"] == ["FINISHED"]


def reopen_marker(path, expected_location):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.open_mainfile(filepath=str(path))
    assert tuple(bpy.data.objects["SavedMarker"].location) == expected_location


def test_native_save_as_then_current_save_reopens_latest_state(save_fixture, tmp_path):
    path = tmp_path / "current.blend"
    assert_verified(save_fixture(str(path)), path)
    bpy.data.objects["SavedMarker"].location = (1, 2, 3)
    assert_verified(save_fixture(), path)
    reopen_marker(path, (1, 2, 3))


@pytest.mark.parametrize("relative", ["relative.blend", "./relative.blend", "folder/../relative.blend"])
def test_native_relative_filepath(save_fixture, tmp_path, monkeypatch, relative):
    (tmp_path / "folder").mkdir()
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "relative.blend"
    assert_verified(save_fixture(relative), path)
    reopen_marker(path, (0, 0, 0))


def test_native_blender_relative_filepath_uses_previous_scene_base(save_fixture, tmp_path):
    source = tmp_path / "source.blend"
    assert_verified(save_fixture(str(source)), source)
    target = tmp_path / "nested" / "target.blend"
    target.parent.mkdir()
    assert_verified(save_fixture("//nested/target.blend"), target)
    reopen_marker(target, (0, 0, 0))


def test_native_extensionless_filepath_reports_actual_saved_path(save_fixture, tmp_path):
    result = save_fixture(str(tmp_path / "extensionless"))
    assert result["success"], result
    actual = Path(result["context"]["filepath"])
    assert actual in (tmp_path / "extensionless", tmp_path / "extensionless.blend")
    assert_verified(result, actual)
    reopen_marker(actual, (0, 0, 0))


@pytest.mark.parametrize("symlink_kind", ["directory", "file"])
def test_native_legal_symlink_destination(save_fixture, tmp_path, symlink_kind):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    if symlink_kind == "directory":
        alias = tmp_path / "alias"
        try:
            alias.symlink_to(real_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation unavailable for this test account")
        target = alias / "saved.blend"
    else:
        source = real_dir / "source.blend"
        assert_verified(save_fixture(str(source)), source)
        target = tmp_path / "alias.blend"
        try:
            target.symlink_to(source)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation unavailable for this test account")
    bpy.data.objects["SavedMarker"].location = (4, 5, 6)
    assert_verified(save_fixture(str(target)), target)
    reopen_marker(target, (4, 5, 6))


def test_native_failed_destination_never_reports_success(save_fixture, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_bytes(b"preserved")
    result = save_fixture(str(blocker / "failed.blend"))
    assert not result["success"], result
    assert result["context"]["save_attempted"] is True
    assert result["context"]["mutation_applied"] is None
    assert blocker.read_bytes() == b"preserved"
