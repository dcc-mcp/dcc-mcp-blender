"""Unit tests for the image lifecycle and lighting detail tools (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

LIBRARY_PATH = "src/dcc_mcp_blender/skills/blender-material-library/tools.yaml"
LIGHTING_PATH = "src/dcc_mcp_blender/skills/blender-lighting/tools.yaml"
LIBRARY = "blender-material-library"
LIGHTING = "blender-lighting"


class _ImageCollection(list):
    def get(self, name):
        for image in self:
            if getattr(image, "name", None) == name:
                return image
        return None


class _ObjectCollection(list):
    def get(self, name):
        for obj in self:
            if getattr(obj, "name", None) == name:
                return obj
        return None


class _Pixels(list):
    """Stands in for Blender's lazily loaded pixel collection.

    Indexing materialises the data; len() does not. A probe on every supported
    Blender confirmed len() already reports the full size while has_data is
    still False, so length is not a usable signal.

    Assigning image.filepath is what discards the decoded buffer, which is why
    the decode has to happen after that assignment rather than before it.
    """

    def __init__(self, owner, count=16):
        super().__init__([0.0] * count)
        self._owner = owner

    def __getitem__(self, index):
        self._owner.has_data = True
        return super().__getitem__(index)


class _Image:
    """Stand-in for bpy.types.Image.

    filepath is a real property because assigning it is what discards the
    decoded pixel buffer in Blender. That interaction is the whole point of the
    ordering in save_image, so the fake has to reproduce it: a SimpleNamespace
    cannot, since its type is immutable.
    """

    def __init__(self, name, filepath, size, source, packed, tiles):
        self.name = name
        self._filepath = filepath
        self.filepath_raw = filepath
        self.size = list(size)
        self.source = source
        self.is_dirty = False
        self.has_data = False
        self.colorspace_settings = SimpleNamespace(name="sRGB")
        self.packed_file = SimpleNamespace() if packed else None
        self.tiles = list(tiles)
        self.pixels = _Pixels(self)
        self.reload = MagicMock()
        # Blender refuses to save an image with no decoded data, so honour
        # has_data. Without this the fake would happily "save" an undecodeable
        # image and the ordering bug would go unnoticed.
        self.save = MagicMock(side_effect=self._save)
        self.save_render = MagicMock(side_effect=self._save_render)
        self.pack = MagicMock(side_effect=lambda: setattr(self, "packed_file", SimpleNamespace()))
        self.unpack = MagicMock(side_effect=lambda method="USE_ORIGINAL": setattr(self, "packed_file", None))
        # Log which method wrote, so a test can assert the explicit-path route
        # uses save_render and the in-place route uses save.
        self.writes = []

    def _save(self):
        """Mirror Blender: refuse without decoded data, otherwise write.

        Writing to self.filepath is what makes the ordering meaningful. If this
        only raised, a decode that happened too early would still look fine
        because nothing would ever be written either way.
        """
        if not self.has_data:
            raise RuntimeError(f"Image {self.name!r} does not have any image data")
        self._write(Path(self._filepath), "save")

    def _save_render(self, filepath):
        """Like save(), but writes to an explicit path without re-associating."""
        if not self.has_data:
            raise RuntimeError(f"Image {self.name!r} does not have any image data")
        self._write(Path(filepath), "save_render")

    def _write(self, target, method):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"SAVED")
        self.writes.append(method)

    @property
    def filepath(self):
        return self._filepath

    @filepath.setter
    def filepath(self, value):
        if value != self._filepath:
            self.has_data = False
        self._filepath = value


def _make_image(name="Tex", filepath="/tmp/tex.png", size=(64, 32), packed=False, source="FILE", tiles=()):
    return _Image(name, filepath, size, source, packed, tiles)


def _bpy_with_images(*images, collections=()):
    bpy = make_mock_bpy()
    bpy.data.images = _ImageCollection(images)
    bpy.data.images.load = MagicMock(
        side_effect=lambda path, check_existing=True: _make_image(name=Path(path).stem, filepath=path)
    )
    bpy.data.collections = _ObjectCollection(collections)
    bpy.data.objects = _ObjectCollection()
    return bpy


def _call(skill, script, bpy, **kwargs):
    return load_and_call(f"{skill}/scripts/{script}.py", bpy, **kwargs)


# ---------------------------------------------------------------------------
# load_image
# ---------------------------------------------------------------------------


def test_load_image_reads_from_disk(tmp_path):
    path = tmp_path / "wood.png"
    path.write_text("x", encoding="utf-8")

    result = _call(LIBRARY, "load_image", _bpy_with_images(), file_path=str(path))
    assert result["success"] is True, result.get("error")
    assert result["context"]["image"]["name"] == "wood"
    assert result["context"]["image"]["filepath"] == str(path)


def test_load_image_rejects_a_missing_file(tmp_path):
    result = _call(LIBRARY, "load_image", _bpy_with_images(), file_path=str(tmp_path / "nope.png"))
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_load_image_applies_a_name_override(tmp_path):
    path = tmp_path / "wood.png"
    path.write_text("x", encoding="utf-8")

    result = _call(LIBRARY, "load_image", _bpy_with_images(), file_path=str(path), image_name="FloorMap")
    assert result["success"] is True
    assert result["context"]["image"]["name"] == "FloorMap"


def test_load_image_reports_an_unknown_color_space(tmp_path):
    """A colour space Blender rejects must be reported, not silently dropped."""
    path = tmp_path / "wood.png"
    path.write_text("x", encoding="utf-8")
    image = _make_image()

    class _RejectingSettings:
        name = "sRGB"

        def __setattr__(self, key, value):
            raise TypeError("unknown colorspace")

    image.colorspace_settings = _RejectingSettings()
    bpy = _bpy_with_images()
    bpy.data.images.load = MagicMock(return_value=image)
    result = _call(LIBRARY, "load_image", bpy, file_path=str(path), color_space="Bogus")
    assert result["success"] is True
    assert result["context"]["not_applied"] == ["color_space"]


# ---------------------------------------------------------------------------
# save / pack / unpack
# ---------------------------------------------------------------------------


def test_save_image_writes_in_place_without_a_destination(tmp_path):
    """No file_path means write back over the image's own file, using save()."""
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))
    _ = image.pixels[0]  # decode first, as Blender would after a read

    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True, result.get("error")
    assert result["context"]["method"] == "save"
    assert image.writes == ["save"]
    assert source.read_bytes() == b"SAVED"

    # The image must still point at its own file. Assigning filepath is what
    # invalidated the pixel buffer, so it must not happen on either path.
    assert Path(image.filepath) == source


def test_save_image_writes_a_copy_through_save_render(tmp_path):
    """An explicit file_path goes through save_render, which does not re-point."""
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))
    _ = image.pixels[0]

    target = tmp_path / "out.png"
    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex", file_path=str(target))
    assert result["success"] is True, result.get("error")
    assert result["context"]["method"] == "save_render"
    assert image.writes == ["save_render"]
    assert target.is_file(), "the copy must exist at the requested path"
    assert Path(image.filepath) == source, "the datablock must not be re-pointed"
    assert result["context"]["has_data"] is True


def test_save_image_reports_the_written_size(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))
    _ = image.pixels[0]

    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex", file_path=str(tmp_path / "o.png"))
    assert result["success"] is True, result.get("error")
    assert result["context"]["size_bytes"] == len(b"SAVED")


def test_save_image_fails_when_blender_writes_nothing(tmp_path):
    """A save that leaves no file is a failure, never a success."""
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))
    image.save_render = MagicMock()  # no-op: nothing is written
    _ = image.pixels[0]

    result = _call(
        LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex", file_path=str(tmp_path / "out.png")
    )
    assert result["success"] is False
    assert "not saved" in result["message"].lower()
    assert str(tmp_path / "out.png") in result["error"]


def test_save_image_reports_an_empty_pixel_collection(tmp_path):
    """An image whose pixels vanish is a failure with the state included.

    Assigning filepath empties the collection in Blender, so reading one pixel
    can raise IndexError. Swallowing it and reporting has_data is what lets the
    next run diagnose rather than guess.
    """
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))

    class _EmptyPixels(list):
        def __getitem__(self, index):
            raise IndexError("index out of range")

    image.pixels = _EmptyPixels()

    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex", file_path=str(tmp_path / "o.png"))
    assert result["success"] is False
    assert "no pixel data" in result["message"].lower()
    assert "has_data" in result["context"], "the failure must report the state it measured"
    image.save_render.assert_not_called()


def test_save_image_reports_pixels_that_never_materialise(tmp_path):
    """A read that succeeds but leaves has_data False is also a failure."""
    source = tmp_path / "source.png"
    source.write_bytes(b"ORIGINAL")
    image = _make_image(filepath=str(source))

    class _Unmaterialising(list):
        def __init__(self):
            super().__init__([0.0] * 16)

        def __getitem__(self, index):
            return super().__getitem__(index)  # never sets has_data

    image.pixels = _Unmaterialising()
    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex", file_path=str(tmp_path / "o.png"))
    assert result["success"] is False
    assert "no pixel data" in result["message"].lower()
    image.save_render.assert_not_called()


def test_save_image_reports_a_missing_image():
    result = _call(LIBRARY, "save_image", _bpy_with_images(), image_name="Ghost")
    assert result["success"] is False
    assert "image not found" in result["message"].lower()


def test_save_image_requires_a_path_when_the_image_has_none():
    image = _make_image(filepath="")
    result = _call(LIBRARY, "save_image", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is False
    assert "no file path" in result["message"].lower()


def test_pack_image_embeds_the_file():
    image = _make_image()
    result = _call(LIBRARY, "pack_image", _bpy_with_images(image), image_name="Tex")

    assert result["success"] is True, result.get("error")
    assert result["context"]["packed"] is True
    assert image.packed_file is not None


def test_pack_image_is_idempotent_when_already_packed():
    image = _make_image(packed=True)
    result = _call(LIBRARY, "pack_image", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["changed"] is False
    image.pack.assert_not_called()


def test_pack_image_fails_when_blender_does_not_pack():
    """A pack call that leaves nothing packed must be reported as a failure."""
    image = _make_image()
    image.pack = MagicMock()  # no-op
    result = _call(LIBRARY, "pack_image", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is False
    assert "not packed" in result["message"].lower()


def test_unpack_image_writes_to_disk():
    image = _make_image(packed=True)
    result = _call(LIBRARY, "unpack_image", _bpy_with_images(image), image_name="Tex", method="WRITE_LOCAL")

    assert result["success"] is True, result.get("error")
    assert image.packed_file is None
    assert result["context"]["method"] == "WRITE_LOCAL"


def test_unpack_image_rejects_an_unknown_method():
    image = _make_image(packed=True)
    result = _call(LIBRARY, "unpack_image", _bpy_with_images(image), image_name="Tex", method="NOPE")
    assert result["success"] is False
    assert "unsupported unpack method" in result["message"].lower()


def test_unpack_image_is_a_noop_when_not_packed():
    image = _make_image(packed=False)
    result = _call(LIBRARY, "unpack_image", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["changed"] is False
    image.unpack.assert_not_called()


# ---------------------------------------------------------------------------
# status / tiles
# ---------------------------------------------------------------------------


def test_image_file_status_reports_external(tmp_path):
    path = tmp_path / "tex.png"
    path.write_text("x", encoding="utf-8")
    image = _make_image(filepath=str(path))

    result = _call(LIBRARY, "image_file_status", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["state"] == "external"
    assert result["context"]["exists_on_disk"] is True
    assert result["context"]["packed"] is False


def test_image_file_status_reports_missing():
    image = _make_image(filepath="/does/not/exist.png")
    result = _call(LIBRARY, "image_file_status", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["state"] == "missing"


def test_image_file_status_reports_packed():
    image = _make_image(packed=True)
    result = _call(LIBRARY, "image_file_status", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["state"] == "packed"


def test_image_file_status_reports_unsaved():
    image = _make_image(filepath="")
    result = _call(LIBRARY, "image_file_status", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["state"] == "unsaved"


def test_list_image_tiles_reports_non_udim():
    image = _make_image(tiles=[SimpleNamespace(number=0, label="")])
    result = _call(LIBRARY, "list_image_tiles", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["is_udim"] is False
    assert result["context"]["count"] == 1


def test_list_image_tiles_reports_udim():
    image = _make_image(source="UDIM", tiles=[SimpleNamespace(number=1001, label="1001")])
    result = _call(LIBRARY, "list_image_tiles", _bpy_with_images(image), image_name="Tex")
    assert result["success"] is True
    assert result["context"]["is_udim"] is True
    assert result["context"]["tiles"][0]["number"] == 1001


def test_list_image_tiles_reports_a_missing_image():
    result = _call(LIBRARY, "list_image_tiles", _bpy_with_images(), image_name="Ghost")
    assert result["success"] is False
    assert "image not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# IES
# ---------------------------------------------------------------------------


def _light_object(name="Spot", light_type="SPOT", **light_attrs):
    light = SimpleNamespace(type=light_type, **light_attrs)
    return SimpleNamespace(name=name, type="LIGHT", data=light)


def _bpy_with_lights(*objects, collections=()):
    bpy = make_mock_bpy()
    bpy.data.objects = _ObjectCollection(objects)
    bpy.data.collections = _ObjectCollection(collections)
    bpy.data.images = _ImageCollection()
    return bpy


def test_set_light_ies_attaches_a_profile(tmp_path):
    path = tmp_path / "profile.ies"
    path.write_text("x", encoding="utf-8")
    obj = _light_object(ies_file="", ies_strength=1.0)

    result = _call(
        LIGHTING,
        "set_light_ies",
        _bpy_with_lights(obj),
        light_name="Spot",
        ies_file_path=str(path),
        ies_strength=2.5,
    )
    assert result["success"] is True, result.get("error")
    assert obj.data.ies_file == str(path)
    assert obj.data.ies_strength == 2.5


def test_set_light_ies_rejects_a_missing_file(tmp_path):
    obj = _light_object(ies_file="")
    result = _call(
        LIGHTING, "set_light_ies", _bpy_with_lights(obj), light_name="Spot", ies_file_path=str(tmp_path / "n.ies")
    )
    assert result["success"] is False
    assert "ies file not found" in result["message"].lower()
    assert obj.data.ies_file == ""


def test_set_light_ies_rejects_non_spot_lights(tmp_path):
    path = tmp_path / "profile.ies"
    path.write_text("x", encoding="utf-8")
    obj = _light_object(light_type="POINT", ies_file="")

    result = _call(LIGHTING, "set_light_ies", _bpy_with_lights(obj), light_name="Spot", ies_file_path=str(path))
    assert result["success"] is False
    assert "not a spot light" in result["message"].lower()
    assert obj.data.ies_file == ""


def test_set_light_ies_reports_a_light_without_ies_support(tmp_path):
    """A light with no ies_file property must be reported, not silently skipped."""
    path = tmp_path / "profile.ies"
    path.write_text("x", encoding="utf-8")
    obj = _light_object()  # no ies_file attribute at all
    assert not hasattr(obj.data, "ies_file")

    result = _call(LIGHTING, "set_light_ies", _bpy_with_lights(obj), light_name="Spot", ies_file_path=str(path))
    assert result["success"] is False
    assert "unavailable" in result["message"].lower()
    assert "ies_file" in result["error"]


def test_set_light_ies_can_clear():
    obj = _light_object(ies_file="/tmp/p.ies", ies_strength=1.0)
    result = _call(LIGHTING, "set_light_ies", _bpy_with_lights(obj), light_name="Spot", clear=True)
    assert result["success"] is True
    assert obj.data.ies_file == ""
    assert result["context"]["ies_file"] is None


def test_set_light_ies_rejects_negative_strength():
    obj = _light_object(ies_file="", ies_strength=1.0)
    result = _call(LIGHTING, "set_light_ies", _bpy_with_lights(obj), light_name="Spot", ies_strength=-1)
    assert result["success"] is False
    assert "strength" in result["message"].lower()


# ---------------------------------------------------------------------------
# light linking
# ---------------------------------------------------------------------------


def _linking_object(name="Spot", light_type="SPOT"):
    linking = SimpleNamespace(receiver_collection=None, blocker_collection=None)
    obj = _light_object(name=name, light_type=light_type, light_linking=linking)
    return obj


def test_set_light_linking_assigns_receiver_and_blocker():
    obj = _linking_object()
    receivers = SimpleNamespace(name="Chars")
    blockers = SimpleNamespace(name="Occluders")

    result = _call(
        LIGHTING,
        "set_light_linking",
        _bpy_with_lights(obj, collections=[receivers, blockers]),
        light_name="Spot",
        receiver_collection="Chars",
        blocker_collection="Occluders",
    )
    assert result["success"] is True, result.get("error")
    assert obj.data.light_linking.receiver_collection is receivers
    assert obj.data.light_linking.blocker_collection is blockers
    assert result["context"]["receiver"] == "Chars"
    assert result["context"]["blocker"] == "Occluders"


def test_set_light_linking_reports_a_missing_collection():
    obj = _linking_object()
    result = _call(
        LIGHTING,
        "set_light_linking",
        _bpy_with_lights(obj),
        light_name="Spot",
        receiver_collection="Ghost",
    )
    assert result["success"] is False
    assert "collection not found" in result["message"].lower()
    assert obj.data.light_linking.receiver_collection is None


def test_set_light_linking_reports_a_light_without_support():
    """Older lights have no light_linking; that must be an explicit error."""
    obj = _light_object()  # no light_linking attribute
    assert not hasattr(obj.data, "light_linking")

    result = _call(LIGHTING, "set_light_linking", _bpy_with_lights(obj), light_name="Spot", receiver_collection="Chars")
    assert result["success"] is False
    assert "unavailable" in result["message"].lower()
    assert "4.1" in result["error"]


def test_set_light_linking_requires_a_change():
    obj = _linking_object()
    result = _call(LIGHTING, "set_light_linking", _bpy_with_lights(obj), light_name="Spot")
    assert result["success"] is False
    assert "no linking change" in result["message"].lower()


def test_set_light_linking_can_clear():
    obj = _linking_object()
    obj.data.light_linking.receiver_collection = SimpleNamespace(name="Chars")

    result = _call(LIGHTING, "set_light_linking", _bpy_with_lights(obj), light_name="Spot", clear=True)
    assert result["success"] is True
    assert result["context"]["receiver"] is None


def test_set_light_linking_rejects_non_lights():
    obj = SimpleNamespace(name="Cube", type="MESH", data=None)
    result = _call(LIGHTING, "set_light_linking", _bpy_with_lights(obj), light_name="Cube", receiver_collection="Chars")
    assert result["success"] is False
    assert "not a light" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_the_new_tools():
    library = yaml.safe_load(Path(LIBRARY_PATH).read_text(encoding="utf-8"))
    lighting = yaml.safe_load(Path(LIGHTING_PATH).read_text(encoding="utf-8"))
    names = {tool["name"] for tool in library["tools"]}
    assert {
        "load_image",
        "save_image",
        "pack_image",
        "unpack_image",
        "image_file_status",
        "list_image_tiles",
    }.issubset(names)
    light_names = {tool["name"] for tool in lighting["tools"]}
    assert {"set_light_ies", "set_light_linking"}.issubset(light_names)


def test_new_tools_declare_required_contract_fields():
    docs = {
        LIBRARY: yaml.safe_load(Path(LIBRARY_PATH).read_text(encoding="utf-8")),
        LIGHTING: yaml.safe_load(Path(LIGHTING_PATH).read_text(encoding="utf-8")),
    }
    expected = {
        LIBRARY: (
            "load_image",
            "save_image",
            "pack_image",
            "unpack_image",
            "image_file_status",
            "list_image_tiles",
        ),
        LIGHTING: ("set_light_ies", "set_light_linking"),
    }
    for skill, names in expected.items():
        tools = {tool["name"]: tool for tool in docs[skill]["tools"]}
        for name in names:
            tool = tools[name]
            assert tool["execution"] == "sync", name
            assert tool["affinity"] == "main", name
            source = Path("src/dcc_mcp_blender/skills") / skill / tool["source_file"]
            assert source.is_file(), f"missing source script: {source}"
            assert tool["read_only"] is tool["annotations"]["read_only_hint"], name


def test_new_tools_are_not_flagged_destructive():
    """None of these delete data; packing and unpacking move files only."""
    library = {tool["name"]: tool for tool in yaml.safe_load(Path(LIBRARY_PATH).read_text(encoding="utf-8"))["tools"]}
    for name in ("load_image", "save_image", "pack_image", "unpack_image", "image_file_status", "list_image_tiles"):
        assert library[name]["destructive"] is False, name
        assert library[name]["annotations"]["destructive_hint"] is False, name
