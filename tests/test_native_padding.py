from pathlib import Path
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _portable_scene as m


class Params:
    def __init__(self, length=128):
        self.memory = bytearray(b"/workspace/example-fixture/scene/home\0".ljust(128, b"\0"))
        self.bl_rna = SimpleNamespace(properties={"directory": SimpleNamespace(length_max=length)})

    @property
    def directory(self):
        return bytes(self.memory).split(b"\0")[0]

    @directory.setter
    def directory(self, value):
        self.memory[: len(value) + 1] = value + b"\0"


def test_setter_shortening_reproduces_stale_native_tail():
    p = Params()
    p.directory = b"//"
    assert b"rkspace/example-fixture" in p.memory
    assert m._path_audit(bytes(p.memory))


def test_bounded_native_overwrite_removes_stale_tail():
    p = Params()
    m._clear_browser_directory(p)
    assert p.directory == b"//"
    assert b"workspace" not in p.memory and b"rkspace" not in p.memory
    assert set(p.memory[3:-1]) == {ord("~")}
    assert not m._path_audit(bytes(p.memory))


@pytest.mark.parametrize("bound", [0, 2, 65537, None, True])
def test_unrecognized_bound_fails_closed(bound):
    with pytest.raises(ValueError):
        m._clear_browser_directory(Params(bound))


def test_private_render_path_rejected():
    with pytest.raises(ValueError):
        m._relative_render_path("/workspace/private/output.png")


def fake_bpy(monkeypatch, content=b"BLENDER-v430-neutral"):
    import sys

    params = Params()
    scene = SimpleNamespace(
        render=SimpleNamespace(
            filepath="/workspace/private/render.png",
            bl_rna=SimpleNamespace(properties={"filepath": SimpleNamespace(length_max=1024)}),
        )
    )
    space = SimpleNamespace(type="FILE_BROWSER", params=params)
    data = SimpleNamespace(
        libraries=[],
        texts=[],
        movieclips=[],
        sounds=[],
        volumes=[],
        cache_files=[],
        images=[],
        objects=[],
        materials=[],
        screens=[SimpleNamespace(areas=[SimpleNamespace(spaces=[space])])],
    )

    def save(**kwargs):
        Path(kwargs["filepath"]).write_bytes(content)

    bpy = SimpleNamespace(
        data=data, context=SimpleNamespace(scene=scene), ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=save))
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return params, scene


def test_save_restores_logical_fields_and_publishes_new_copy(tmp_path, monkeypatch):
    params, scene = fake_bpy(monkeypatch)
    original = params.directory
    result = m.save_portable_scene_copy(str(tmp_path / "clean.blend"), str(tmp_path))
    assert result["success"] is True
    assert (tmp_path / "clean.blend").read_bytes() == b"BLENDER-v430-neutral"
    assert params.directory == original and scene.render.filepath == "/workspace/private/render.png"
    assert not list(tmp_path.glob(".blend-publish-*"))


def test_failed_guard_restores_fields_and_removes_staging(tmp_path, monkeypatch):
    params, scene = fake_bpy(monkeypatch, b"BLENDER-v430-\0//\0rkspace/example-fixture\0")
    original = params.directory
    result = m.save_portable_scene_copy(str(tmp_path / "clean.blend"), str(tmp_path))
    assert result["success"] is False and not (tmp_path / "clean.blend").exists()
    assert params.directory == original and scene.render.filepath == "/workspace/private/render.png"
    assert not list(tmp_path.glob(".blend-publish-*"))


def test_cancellation_restores_fields_without_publishing(tmp_path, monkeypatch):
    params, scene = fake_bpy(monkeypatch)
    original = params.directory
    calls = []

    def cancel():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("cancelled")

    monkeypatch.setattr(m, "check_dcc_cancelled", cancel)
    result = m.save_portable_scene_copy(str(tmp_path / "clean.blend"), str(tmp_path))
    assert result["success"] is False and not (tmp_path / "clean.blend").exists()
    assert params.directory == original and scene.render.filepath == "/workspace/private/render.png"
    assert not list(tmp_path.glob(".blend-publish-*"))
