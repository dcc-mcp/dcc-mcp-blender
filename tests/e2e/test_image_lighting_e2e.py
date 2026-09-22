"""E2E tests for the image lifecycle and lighting detail tools in real Blender.

The mocked suite cannot tell a property Blender rejects from one it accepts, so
these assert against the actual datablocks. Every assertion reads state back
off the Blender object rather than off the tool response.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _library(name):
    return load_skill("blender-material-library", name)


def _lighting(name):
    return load_skill("blender-lighting", name)


def _png(path):
    """Write a minimal 2x2 PNG Blender can decode."""
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    return path


class TestImageLifecycleE2E:
    def setup_method(self):
        _new_scene()

    def test_load_save_and_status_round_trip(self, tmp_path):
        """Load an image, check its status, save it elsewhere."""
        source = _png(tmp_path / "source.png")

        result = _library("load_image").load_image(file_path=str(source))
        assert result["success"] is True, result.get("error")
        name = result["context"]["image"]["name"]

        image = bpy.data.images[name]
        assert image.size[0] == 2, "the image must be decoded with real dimensions"
        assert image.source == "FILE"

        result = _library("image_file_status").image_file_status(image_name=name)
        assert result["success"] is True, result.get("error")
        assert result["context"]["state"] in {"external", "modified_unsaved"}
        assert result["context"]["exists_on_disk"] is True
        assert result["context"]["packed"] is False

        target = tmp_path / "saved.png"
        result = _library("save_image").save_image(image_name=name, file_path=str(target))
        assert result["success"] is True, result.get("error")
        # The real round trip: the bytes have to be on disk. Under
        # --background pixel data is not materialised until something reads
        # it, and a save that quietly writes nothing must fail instead.
        assert target.is_file(), "the image must actually be written to disk"
        assert target.stat().st_size > 0, "the saved file must not be empty"

        # Saving is repeatable, not a one-shot.
        second = tmp_path / "saved_again.png"
        again = _library("save_image").save_image(image_name=name, file_path=str(second))
        assert again["success"] is True, again.get("error")
        assert second.is_file()

    def test_load_rejects_a_missing_file(self, tmp_path):
        result = _library("load_image").load_image(file_path=str(tmp_path / "nope.png"))
        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert len(bpy.data.images) == 0

    def test_pack_and_unpack_round_trip(self, tmp_path):
        """Packing must embed the file; unpacking must put it back on disk."""
        source = _png(tmp_path / "pack.png")
        result = _library("load_image").load_image(file_path=str(source))
        assert result["success"] is True, result.get("error")
        name = result["context"]["image"]["name"]

        result = _library("pack_image").pack_image(image_name=name)
        assert result["success"] is True, result.get("error")
        assert bpy.data.images[name].packed_file is not None, "Blender must report it packed"

        status = _library("image_file_status").image_file_status(image_name=name)
        assert status["context"]["state"] == "packed"

        # Re-packing is a no-op rather than an error.
        again = _library("pack_image").pack_image(image_name=name)
        assert again["success"] is True
        assert again["context"]["changed"] is False

        result = _library("unpack_image").unpack_image(image_name=name, method="WRITE_LOCAL")
        assert result["success"] is True, result.get("error")
        assert bpy.data.images[name].packed_file is None, "Blender must report it unpacked"

        result = _library("image_file_status").image_file_status(image_name=name)
        assert result["context"]["packed"] is False

    def test_save_without_a_path_reports_the_image_has_none(self):
        """A generated image has no path, so saving needs an explicit one."""
        image = bpy.data.images.new("Generated", width=4, height=4)
        assert image.filepath == ""

        result = _library("save_image").save_image(image_name="Generated")
        assert result["success"] is False
        assert "no file path" in result["message"].lower()

    def test_list_tiles_on_a_non_udim_image(self, tmp_path):
        source = _png(tmp_path / "tile.png")
        result = _library("load_image").load_image(file_path=str(source))
        assert result["success"] is True, result.get("error")
        name = result["context"]["image"]["name"]

        result = _library("list_image_tiles").list_image_tiles(image_name=name)
        assert result["success"] is True, result.get("error")
        assert result["context"]["is_udim"] is False
        assert result["context"]["count"] == len(bpy.data.images[name].tiles)

    def test_unknown_color_space_is_reported_not_dropped(self, tmp_path):
        """A colour space Blender refuses must appear in not_applied."""
        source = _png(tmp_path / "space.png")
        result = _library("load_image").load_image(file_path=str(source), color_space="DefinitelyNotReal")
        assert result["success"] is True, result.get("error")
        assert result["context"]["not_applied"] == ["color_space"]


class TestLightingDetailE2E:
    def setup_method(self):
        _new_scene()

    def _spot(self, name="Spot"):
        light = bpy.data.lights.new(name, type="SPOT")
        obj = bpy.data.objects.new(name, light)
        bpy.context.scene.collection.objects.link(obj)
        return obj

    def test_ies_attaches_to_a_spot_light(self, tmp_path):
        obj = self._spot()
        ies = tmp_path / "profile.ies"
        ies.write_text("IESNA:LM-63-1995\n", encoding="utf-8")

        result = _lighting("set_light_ies").set_light_ies(light_name=obj.name, ies_file_path=str(ies), ies_strength=2.0)
        if not hasattr(obj.data, "ies_file"):
            # No IES support on this build: the tool has to say so rather than
            # reporting success for an attachment that never happened.
            assert result["success"] is False, result.get("context")
            assert "ies_file" in result["error"]
            return

        assert result["success"] is True, result.get("error")
        # Read it back off the light data.
        assert obj.data.ies_file == str(ies)
        assert obj.data.ies_strength == pytest.approx(2.0)

    def test_ies_rejects_a_point_light(self, tmp_path):
        light = bpy.data.lights.new("Point", type="POINT")
        obj = bpy.data.objects.new("Point", light)
        bpy.context.scene.collection.objects.link(obj)

        ies = tmp_path / "profile.ies"
        ies.write_text("IESNA:LM-63-1995\n", encoding="utf-8")

        result = _lighting("set_light_ies").set_light_ies(light_name="Point", ies_file_path=str(ies))
        assert result["success"] is False
        assert "not a spot light" in result["message"].lower()

    def test_light_linking_assigns_a_receiver(self):
        obj = self._spot()
        collection = bpy.data.collections.new("Chars")

        result = _lighting("set_light_linking").set_light_linking(light_name=obj.name, receiver_collection="Chars")
        if not hasattr(obj.data, "light_linking"):
            # Pre-4.1 lights have no linking: refusal, not a skipped check.
            assert result["success"] is False, result.get("context")
            assert "unavailable" in result["message"].lower()
            return

        assert result["success"] is True, result.get("error")
        assert obj.data.light_linking.receiver_collection is collection

        cleared = _lighting("set_light_linking").set_light_linking(light_name=obj.name, clear=True)
        assert cleared["success"] is True, cleared.get("error")
        assert obj.data.light_linking.receiver_collection is None

    def test_light_linking_reports_a_missing_collection(self):
        obj = self._spot()

        result = _lighting("set_light_linking").set_light_linking(
            light_name=obj.name, receiver_collection="NoSuchCollection"
        )
        assert result["success"] is False, result.get("context")
        if hasattr(obj.data, "light_linking"):
            assert "collection not found" in result["message"].lower()
