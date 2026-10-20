"""Save contract fault injection; these doubles are not real Blender evidence."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from jsonschema import Draft7Validator

from tests.conftest import SKILLS_ROOT, load_and_call

SCRIPT = "blender-scene/scripts/save_scene.py"


@pytest.fixture(autouse=True)
def isolated_working_directory(tmp_path, monkeypatch):
    """Even negative tests must never leave files in the checkout."""
    monkeypatch.chdir(tmp_path)


def host(tmp_path):
    data = SimpleNamespace(filepath="")

    def abspath(value):
        if value.startswith("//"):
            return os.path.join(os.path.dirname(data.filepath) if data.filepath else str(tmp_path), value[2:])
        return os.path.abspath(value)

    def save_as(filepath):
        target = abspath(filepath)
        if not target.lower().endswith(".blend"):
            target += ".blend"
        Path(target).write_bytes(b"BLENDER-test-fixture")
        data.filepath = target
        return {"FINISHED"}

    def save_current():
        Path(data.filepath).write_bytes(b"BLENDER-updated-fixture")
        return {"FINISHED"}

    return SimpleNamespace(
        data=data,
        path=SimpleNamespace(abspath=abspath),
        ops=SimpleNamespace(
            wm=SimpleNamespace(save_as_mainfile=Mock(side_effect=save_as), save_mainfile=Mock(side_effect=save_current))
        ),
    )


def call(bpy, **kwargs):
    return load_and_call(SCRIPT, bpy, **kwargs)


@pytest.mark.parametrize(
    "operator_result",
    [
        {"CANCELLED"},
        {"RUNNING_MODAL"},
        {"FINISHED", "CANCELLED"},
        {"FINISHED", "RUNNING_MODAL"},
        {"FINISHED", "PASS_THROUGH"},
        set(),
        None,
        "FINISHED",
        ["FINISHED"],
    ],
)
@pytest.mark.parametrize("save_as", [True, False])
def test_nonfinished_operator_cannot_report_success_even_with_old_file(tmp_path, operator_result, save_as):
    bpy = host(tmp_path)
    path = tmp_path / "existing.blend"
    path.write_bytes(b"old-file-is-not-new-save-proof")
    bpy.data.filepath = str(path)
    operator = bpy.ops.wm.save_as_mainfile if save_as else bpy.ops.wm.save_mainfile
    operator.side_effect = None
    operator.return_value = operator_result
    result = call(bpy, **({"filepath": str(path)} if save_as else {}))
    assert not result["success"], result
    assert path.read_bytes() == b"old-file-is-not-new-save-proof"


def test_new_explicit_save_requires_finished_and_file_readback(tmp_path):
    bpy = host(tmp_path)
    path = tmp_path / "new.blend"
    result = call(bpy, filepath=str(path))
    assert result["success"], result
    assert Path(result["context"]["filepath"]).samefile(path)
    assert result["context"]["file_size_bytes"] == path.stat().st_size
    assert result["postcondition"]["verified"] is True
    bpy.ops.wm.save_as_mainfile.assert_called_once_with(filepath=str(path))
    bpy.ops.wm.save_mainfile.assert_not_called()


def test_current_file_save_reports_verified_actual_file(tmp_path):
    bpy = host(tmp_path)
    path = tmp_path / "current.blend"
    bpy.data.filepath = str(path)
    path.write_bytes(b"old")
    result = call(bpy)
    assert result["success"], result
    assert result["context"]["filepath"] == str(path)
    assert path.read_bytes() == b"BLENDER-updated-fixture"
    assert result["postcondition"]["verified"] is True
    bpy.ops.wm.save_mainfile.assert_called_once_with()
    bpy.ops.wm.save_as_mainfile.assert_not_called()


@pytest.mark.parametrize("condition", ["missing", "empty", "directory", "wrong_scene_path", "empty_scene_path"])
def test_finished_without_matching_nonempty_file_is_unverified(tmp_path, condition):
    bpy = host(tmp_path)
    path = tmp_path / "target.blend"
    bpy.ops.wm.save_as_mainfile.side_effect = None
    bpy.ops.wm.save_as_mainfile.return_value = {"FINISHED"}
    bpy.data.filepath = str(path)
    if condition == "empty":
        path.touch()
    elif condition == "directory":
        path.mkdir()
    elif condition in ("wrong_scene_path", "empty_scene_path"):
        path.write_bytes(b"existing-target")
        other = tmp_path / "other.blend"
        other.write_bytes(b"other-scene")
        bpy.data.filepath = str(other) if condition == "wrong_scene_path" else ""
    result = call(bpy, filepath=str(path))
    assert not result["success"], result
    assert result["context"]["save_attempted"] is True
    assert result["context"]["mutation_applied"] is None


@pytest.mark.parametrize("path_value", [True, 12, [], {}, "", "  ", "bad\x00path"])
def test_invalid_path_never_calls_save(tmp_path, path_value):
    bpy = host(tmp_path)
    result = call(bpy, filepath=path_value)
    assert not result["success"], result
    bpy.ops.wm.save_as_mainfile.assert_not_called()
    bpy.ops.wm.save_mainfile.assert_not_called()
    assert result["context"]["save_attempted"] is False


def test_unsaved_scene_without_target_never_calls_operator(tmp_path):
    bpy = host(tmp_path)
    result = call(bpy)
    assert not result["success"]
    bpy.ops.wm.save_mainfile.assert_not_called()
    bpy.ops.wm.save_as_mainfile.assert_not_called()


@pytest.mark.parametrize(
    "relative", ["scene.blend", "./scene.blend", "folder/../scene.blend", "//scene.blend", "scene"]
)
def test_relative_and_extension_paths_are_resolved_without_false_failure(tmp_path, monkeypatch, relative):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "folder").mkdir()
    bpy = host(tmp_path)
    result = call(bpy, filepath=relative)
    assert result["success"], result
    assert Path(result["context"]["filepath"]).samefile(tmp_path / "scene.blend")


def test_blender_relative_path_is_resolved_before_save_changes_scene_path(tmp_path):
    bpy = host(tmp_path)
    source = tmp_path / "source"
    target = source / "nested"
    target.mkdir(parents=True)
    bpy.data.filepath = str(source / "original.blend")
    result = call(bpy, filepath="//nested/copied.blend")
    assert result["success"], result
    assert Path(result["context"]["filepath"]).samefile(target / "copied.blend")


@pytest.mark.parametrize("save_as", [True, False])
def test_legal_symlink_directory_is_accepted(tmp_path, save_as):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable for this test account")
    bpy = host(tmp_path)
    path = alias / "scene.blend"
    if save_as:
        original = bpy.ops.wm.save_as_mainfile.side_effect

        def save_through_alias(filepath):
            result = original(filepath)
            bpy.data.filepath = str((real / "scene.blend").resolve())
            return result

        bpy.ops.wm.save_as_mainfile.side_effect = save_through_alias
        result = call(bpy, filepath=str(path))
    else:
        path.write_bytes(b"old")
        bpy.data.filepath = str(path)
        result = call(bpy)
    assert result["success"], result
    assert Path(result["context"]["filepath"]).samefile(path)


def test_replaced_file_symlink_remains_an_authorized_target(tmp_path):
    bpy = host(tmp_path)
    real = tmp_path / "real.blend"
    real.write_bytes(b"source")
    alias = tmp_path / "alias.blend"
    try:
        alias.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable for this test account")

    def replace_link(filepath):
        Path(filepath).unlink()
        Path(filepath).write_bytes(b"new-local-file")
        bpy.data.filepath = filepath
        return {"FINISHED"}

    bpy.ops.wm.save_as_mainfile.side_effect = replace_link
    result = call(bpy, filepath=str(alias))
    assert result["success"], result
    assert real.read_bytes() == b"source"
    assert alias.read_bytes() == b"new-local-file"


def test_operator_exception_does_not_claim_no_side_effects_or_retry(tmp_path):
    bpy = host(tmp_path)
    path = tmp_path / "partial.blend"

    def failed(filepath):
        Path(filepath).write_bytes(b"partial")
        raise RuntimeError("injected save failure")

    bpy.ops.wm.save_as_mainfile.side_effect = failed
    result = call(bpy, filepath=str(path))
    assert not result["success"]
    assert result["context"]["save_attempted"] is True
    assert result["context"]["mutation_applied"] is None
    assert path.read_bytes() == b"partial"
    bpy.ops.wm.save_as_mainfile.assert_called_once()


def test_readback_permission_error_is_not_success_or_automatic_retry(tmp_path, monkeypatch):
    bpy = host(tmp_path)

    def stat_denied(*args, **kwargs):
        raise PermissionError("injected stat denial")

    monkeypatch.setattr(os, "stat", stat_denied)
    result = call(bpy, filepath=str(tmp_path / "created.blend"))
    assert not result["success"], result
    assert result["context"]["save_attempted"] is True
    bpy.ops.wm.save_as_mainfile.assert_called_once()


def test_save_schema_and_metadata_are_explicit():
    tools = yaml.safe_load((SKILLS_ROOT / "blender-scene/tools.yaml").read_text())["tools"]
    tool = next(item for item in tools if item["name"] == "save_scene")
    assert tool["affinity"] == "main" and tool["enforce_thread_affinity"] is True
    schema = tool["input_schema"]
    Draft7Validator.check_schema(schema)
    assert Draft7Validator(schema).is_valid({})
    assert Draft7Validator(schema).is_valid({"filepath": "//scene.blend"})
    assert not Draft7Validator(schema).is_valid({"filepath": True})
    assert not Draft7Validator(schema).is_valid({"filepath": ""})
