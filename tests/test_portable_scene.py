"""Bounded scene-copy contract tests; real native acceptance is separately recorded."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from dcc_mcp_blender import _portable_scene as mod


@pytest.fixture
def native(monkeypatch):
    params = NS(directory=b"/workspace/private-task", bl_rna=NS(properties={"directory": NS(length_max=1024)}))
    render = NS(filepath="/workspace/private-task/render.png", bl_rna=NS(properties={"filepath": NS(length_max=1024)}))
    state = NS(payload=b"BLENDER-v430\0portable geometry\0//renders/hero.png", calls=[])

    def save(**kw):
        state.calls.append(dict(kw, render_path=render.filepath, browser_path=params.directory))
        Path(kw["filepath"]).write_bytes(state.payload)

    data = NS(
        libraries=[],
        texts=[],
        movieclips=[],
        sounds=[],
        volumes=[],
        cache_files=[],
        images=[],
        objects=[],
        materials=[],
        screens=[NS(areas=[NS(spaces=[NS(type="FILE_BROWSER", params=params)])])],
    )
    bpy = NS(data=data, context=NS(scene=NS(render=render)), ops=NS(wm=NS(save_as_mainfile=save)))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setattr(mod, "check_dcc_cancelled", lambda: None)
    return bpy, params, render, state


@pytest.mark.parametrize("path", ["../escape.blend", "bad.txt", "folder/missing.blend"])
def test_invalid_destination(tmp_path, path):
    with pytest.raises(ValueError):
        mod._safe_destination(str(tmp_path / path), str(tmp_path))


def test_existing_output_never_overwritten(tmp_path):
    existing = tmp_path / "existing.blend"
    existing.write_bytes(b"original")
    with pytest.raises(ValueError):
        mod._safe_destination(str(existing), str(tmp_path))
    assert existing.read_bytes() == b"original"


def test_symlink_output_rejected(tmp_path):
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("This Windows process lacks native symlink creation privilege")
        raise
    with pytest.raises(ValueError):
        mod._safe_destination(str(link / "new.blend"), str(tmp_path))


@pytest.mark.parametrize(
    "path", ["/absolute.png", "//../escape.png", "//a/../x.png", "//a//x.png", "//a\\x.png", "//" + ("a" * 241)]
)
def test_relative_render_path_rejects_escape(path):
    with pytest.raises(ValueError):
        mod._relative_render_path(path)


def test_relative_render_path_allowed():
    assert mod._relative_render_path("//renders/hero.png") == "//renders/hero.png"


@pytest.mark.parametrize(
    "leak",
    [b"/workspace/private/a", b"/home/user/a", b"/Users/user/a", b"C:\\Users\\private", b"https://private.example/a"],
)
def test_audit_finds_known_path_forms(leak):
    assert mod._path_audit(b"BLENDER\0" + leak + b"\0")


def test_copy_is_staged_atomic_and_restores_state(tmp_path, native):
    bpy, params, render, state = native
    target = tmp_path / "public.blend"
    result = mod.save_portable_scene_copy(str(target), str(tmp_path))
    assert result["success"] and target.read_bytes() == state.payload
    assert render.filepath == "/workspace/private-task/render.png" and params.directory == b"/workspace/private-task"
    assert state.calls[0]["copy"] and state.calls[0]["relative_remap"] is False
    assert state.calls[0]["render_path"] == "//renders/hero.png" and state.calls[0]["browser_path"] == b"//"
    assert not list(tmp_path.glob(".blend-publish-*"))


def test_failed_audit_never_publishes_or_leaks_paths(tmp_path, native):
    bpy, params, render, state = native
    state.payload += b"\0/workspace/private-task/secret.png"
    result = mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))
    assert not result["success"] and not (tmp_path / "public.blend").exists()
    assert "secret.png" not in str(result)
    assert render.filepath == "/workspace/private-task/render.png" and params.directory == b"/workspace/private-task"
    assert not list(tmp_path.glob(".blend-publish-*"))


@pytest.mark.parametrize("group", ["libraries", "texts", "movieclips", "sounds", "volumes", "cache_files"])
def test_rejects_unsupported_dependency_groups(tmp_path, native, group):
    bpy, params, render, state = native
    setattr(bpy.data, group, [object()])
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]
    assert not state.calls


def test_rejects_unpacked_file_image(tmp_path, native):
    native[0].data.images = [NS(source="FILE", filepath="texture.png", packed_file=None)]
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]


@pytest.mark.parametrize("source", ["SEQUENCE", "MOVIE"])
def test_rejects_indirect_image_dependencies(tmp_path, native, source):
    native[0].data.images = [NS(source=source, filepath="//media/frame.png", packed_file=None)]
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]
    assert not native[3].calls


def test_rejects_external_font(tmp_path, native):
    native[0].data.fonts = [NS(filepath="//fonts/custom.ttf", library=None)]
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]


@pytest.mark.parametrize("group", ["materials", "worlds", "lights", "node_groups"])
@pytest.mark.parametrize("node_type", ["SCRIPT", "TEX_IES"])
def test_rejects_indirect_shader_dependencies(tmp_path, native, group, node_type):
    tree = NS(nodes=[NS(type=node_type, filepath="//lighting/profile.ies")])
    setattr(native[0].data, group, [tree] if group == "node_groups" else [NS(node_tree=tree)])
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]
    assert not list(tmp_path.iterdir())
    assert not native[3].calls


def test_rejects_sequence_editor(tmp_path, native):
    native[0].data.scenes = [NS(sequence_editor=NS())]
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]
    assert not list(tmp_path.iterdir())
    assert not native[3].calls
    assert not native[3].calls


def test_reparse_output_component_rejected(tmp_path, monkeypatch):
    component = tmp_path / "redirect"
    component.mkdir()
    original = Path.lstat

    def attributes(path):
        if path == component:
            return NS(st_file_attributes=0x400, st_mode=original(path).st_mode)
        return original(path)

    monkeypatch.setattr(Path, "lstat", attributes)
    with pytest.raises(ValueError, match="reparse"):
        mod._safe_destination(str(component / "new.blend"), str(tmp_path))


def test_rejects_complex_modifier_and_driver(tmp_path, native):
    bpy = native[0]
    bpy.data.objects = [NS(modifiers=[NS(type="NODES")], animation_data=None)]
    assert not mod.save_portable_scene_copy(str(tmp_path / "a.blend"), str(tmp_path))["success"]
    bpy.data.objects = [NS(modifiers=[], animation_data=NS(drivers=[object()]))]
    assert not mod.save_portable_scene_copy(str(tmp_path / "b.blend"), str(tmp_path))["success"]


def test_native_failure_restores_state(tmp_path, native):
    bpy, params, render, state = native

    def fail(**kw):
        raise RuntimeError("synthetic failure")

    bpy.ops.wm.save_as_mainfile = fail
    assert not mod.save_portable_scene_copy(str(tmp_path / "public.blend"), str(tmp_path))["success"]
    assert render.filepath == "/workspace/private-task/render.png" and params.directory == b"/workspace/private-task"
    assert not list(tmp_path.iterdir())


def test_racing_destination_never_overwritten(tmp_path, native, monkeypatch):
    original_link = mod.os.link
    target = tmp_path / "public.blend"

    def race(source, destination):
        target.write_bytes(b"other writer")
        return original_link(source, destination)

    monkeypatch.setattr(mod.os, "link", race)
    assert not mod.save_portable_scene_copy(str(target), str(tmp_path))["success"]
    assert target.read_bytes() == b"other writer"
    assert native[2].filepath == "/workspace/private-task/render.png"
