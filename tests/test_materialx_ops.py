"""Unit tests for MaterialX import/export ops (bpy faked, XML verified on disk)."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

import pytest

from dcc_mcp_blender._materialx_ops import export_materialx, import_materialx

# Principled BSDF socket set of Blender 4.x, the target of the import mapping.
_PRINCIPLED_SOCKETS = {
    "Base Color": (0.8, 0.8, 0.8, 1.0),
    "Metallic": 0.0,
    "Roughness": 0.5,
    "IOR": 1.5,
    "Alpha": 1.0,
    "Normal": (0.0, 0.0, 0.0),
    "Tangent": (0.0, 0.0, 0.0),
    "Anisotropic": 0.0,
    "Anisotropic Rotation": 0.0,
    "Specular Tint": (1.0, 1.0, 1.0, 1.0),
    "Transmission Weight": 0.0,
    "Emission Strength": 0.0,
    "Emission Color": (1.0, 1.0, 1.0, 1.0),
    "Coat Weight": 0.0,
    "Coat Roughness": 0.03,
    "Coat IOR": 1.5,
    "Coat Tint": (1.0, 1.0, 1.0, 1.0),
    "Sheen Weight": 0.0,
    "Sheen Roughness": 0.5,
    "Sheen Tint": (1.0, 1.0, 1.0, 1.0),
    "Subsurface Weight": 0.0,
    "Subsurface Radius": (0.01, 0.01, 0.01),
    "Subsurface Scale": 0.05,
    "Subsurface Anisotropy": 0.0,
    "Thin Film Thickness": 0.0,
    "Thin Film IOR": 1.33,
}


class FakeSocket:
    def __init__(self, name, default_value, is_linked=False):
        self.name = name
        self.identifier = name
        self.default_value = default_value
        self.is_linked = is_linked


class StrictSocket:
    """Socket whose assignment rejects mismatched types the way bpy does.

    The plain :class:`FakeSocket` above accepts anything, so it cannot exercise
    the demote-an-input path. Real Blender raises ``TypeError`` when a scalar
    socket receives a sequence (and the reverse) and ``ValueError`` when an array
    socket receives the wrong dimension, which is exactly what happens when a
    document targets a different Blender generation.
    """

    def __init__(self, name, default_value, is_linked=False):
        self.name = name
        self.identifier = name
        self.is_linked = is_linked
        self._value = default_value

    @property
    def default_value(self):
        return self._value

    @default_value.setter
    def default_value(self, value):
        target = self._value
        if isinstance(target, (tuple, list)):
            if not isinstance(value, (tuple, list)):
                raise TypeError("bpy_struct: sequences of dimension %d expected" % len(target))
            if len(value) != len(target):
                raise ValueError("bpy_struct: sequences of dimension %d expected, got %d" % (len(target), len(value)))
            self._value = tuple(value)
            return
        if isinstance(value, (tuple, list)):
            raise TypeError("bpy_struct: expected a float, got a sequence")
        self._value = value


class FakeNode:
    def __init__(self, name="Principled BSDF"):
        self.name = name
        self.type = "BSDF_PRINCIPLED"
        self.bl_idname = "ShaderNodeBsdfPrincipled"
        self.inputs = {name: FakeSocket(name, value) for name, value in _PRINCIPLED_SOCKETS.items()}


class FakeNodes(dict):
    pass


class FakeNodeTree:
    def __init__(self):
        self.nodes = FakeNodes({"Principled BSDF": FakeNode()})


class FakeMaterial:
    def __init__(self, name):
        self.name = name
        self.use_nodes = False
        self.node_tree = FakeNodeTree()

    def principled(self):
        return self.node_tree.nodes["Principled BSDF"]


class FakeMaterials:
    def __init__(self):
        self._items = {}

    def get(self, name):
        return self._items.get(name)

    def new(self, name):
        unique = name
        index = 1
        while unique in self._items:
            unique = "{}.{:03d}".format(name, index)
            index += 1
        material = FakeMaterial(unique)
        self._items[unique] = material
        return material

    def __iter__(self):
        return iter(list(self._items.values()))

    def __len__(self):
        return len(self._items)


class FakeData:
    def __init__(self):
        self.materials = FakeMaterials()


class FakeBpy:
    def __init__(self):
        self.data = FakeData()


@pytest.fixture
def bpy(monkeypatch):
    fake = FakeBpy()
    monkeypatch.setitem(__import__("sys").modules, "bpy", fake)
    return fake


def add_material(bpy, name, **overrides):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    for socket_name, value in overrides.items():
        material.principled().inputs[socket_name].default_value = value
    return material


def write_document(text, path):
    path.write_text(text, encoding="utf-8")
    return path


_STANDARD_SURFACE_DOC = """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_Copper" type="surfaceshader">
    <input name="base_color" type="color3" value="0.72, 0.45, 0.2" />
    <input name="metalness" type="float" value="0.9" />
    <input name="specular_roughness" type="float" value="0.28" />
    <input name="specular_IOR" type="float" value="1.6" />
    <input name="coat" type="float" value="0.4" />
    <input name="base" type="float" value="1.0" />
  </standard_surface>
  <surfacematerial name="Copper" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Copper" />
  </surfacematerial>
</materialx>
"""


class TestExportMaterialX:
    def test_writes_standard_surface_document(self, bpy, tmp_path):
        add_material(bpy, "Copper", **{"Base Color": (0.72, 0.45, 0.2, 1.0), "Metallic": 0.9, "Roughness": 0.28})
        out = tmp_path / "copper.mtlx"

        result = export_materialx(str(out))

        assert result["success"] is True
        assert result["context"]["node_type"] == "standard_surface"
        assert result["context"]["material_count"] == 1
        assert result["context"]["bytes"] > 0

        root = ET.parse(str(out)).getroot()
        assert root.tag == "materialx"
        assert root.get("version") == "1.39"
        shader = root.find("standard_surface")
        assert shader is not None
        assert shader.get("type") == "surfaceshader"
        values = {element.get("name"): element.get("value") for element in shader.findall("input")}
        assert values["base_color"] == "0.72, 0.45, 0.2"
        assert float(values["metalness"]) == 0.9
        assert float(values["specular_roughness"]) == 0.28

        surface = root.find("surfacematerial")
        assert surface.get("name") == "Copper"
        assert surface.find("input").get("nodename") == shader.get("name")

    def test_appends_mtlx_extension(self, bpy, tmp_path):
        add_material(bpy, "Copper")
        out = tmp_path / "copper"

        result = export_materialx(str(out))

        assert result["success"] is True
        assert (tmp_path / "copper.mtlx").is_file()

    def test_rejects_foreign_extension(self, bpy, tmp_path):
        add_material(bpy, "Copper")

        result = export_materialx(str(tmp_path / "copper.usd"))

        assert result["success"] is False
        assert ".mtlx" in result["error"]

    def test_node_names_are_materialx_identifiers(self, bpy, tmp_path):
        add_material(bpy, "1 Copper Mat.001")
        out = tmp_path / "copper.mtlx"

        result = export_materialx(str(out))

        assert result["success"] is True
        root = ET.parse(str(out)).getroot()
        names = [element.get("name") for element in root]
        assert names
        for name in names:
            assert name[0].isalpha() or name[0] == "_"
            assert all(char.isalnum() or char == "_" for char in name)

    def test_filters_by_material_names(self, bpy, tmp_path):
        add_material(bpy, "Copper")
        add_material(bpy, "Steel")

        result = export_materialx(str(tmp_path / "out.mtlx"), material_names=["Steel"])

        assert result["success"] is True
        assert [item["material"] for item in result["context"]["materials"]] == ["Steel"]

    def test_missing_material_fails(self, bpy, tmp_path):
        add_material(bpy, "Copper")

        result = export_materialx(str(tmp_path / "out.mtlx"), material_names=["Nope"])

        assert result["success"] is False
        assert "Nope" in result["error"]

    def test_rejects_empty_material_names_list(self, bpy, tmp_path):
        result = export_materialx(str(tmp_path / "out.mtlx"), material_names=[])

        assert result["success"] is False
        assert "material_names" in result["error"]

    def test_no_materials_fails(self, bpy, tmp_path):
        result = export_materialx(str(tmp_path / "out.mtlx"))

        assert result["success"] is False
        assert "No materials" in result["message"]

    def test_material_without_nodes_is_skipped(self, bpy, tmp_path):
        material = bpy.data.materials.new("Plain")
        material.use_nodes = False

        result = export_materialx(str(tmp_path / "out.mtlx"))

        assert result["success"] is False
        assert result["context"]["skipped"][0]["material"] == "Plain"

    def test_overwrite_false_keeps_existing_file(self, bpy, tmp_path):
        add_material(bpy, "Copper")
        out = tmp_path / "copper.mtlx"
        out.write_text("untouched", encoding="utf-8")

        result = export_materialx(str(out), overwrite=False)

        assert result["success"] is False
        assert out.read_text(encoding="utf-8") == "untouched"

    def test_linked_socket_reported_not_dropped(self, bpy, tmp_path):
        material = add_material(bpy, "Copper", **{"Base Color": (0.1, 0.2, 0.3, 1.0)})
        material.principled().inputs["Base Color"].is_linked = True

        result = export_materialx(str(tmp_path / "out.mtlx"))

        assert result["success"] is True
        entry = result["context"]["materials"][0]
        assert entry["linked_inputs"] == ["Base Color"]
        assert any("Base Color" in warning for warning in result["context"]["warnings"])
        shader = ET.parse(str(tmp_path / "out.mtlx")).getroot().find("standard_surface")
        values = {element.get("name"): element.get("value") for element in shader.findall("input")}
        assert values["base_color"] == "0.1, 0.2, 0.3"

    def test_emission_color_gets_a_weight(self, bpy, tmp_path):
        material = add_material(bpy, "Glow", **{"Emission Color": (1.0, 0.5, 0.0, 1.0)})
        del material.principled().inputs["Emission Strength"]

        result = export_materialx(str(tmp_path / "out.mtlx"))

        assert result["success"] is True
        shader = ET.parse(str(tmp_path / "out.mtlx")).getroot().find("standard_surface")
        values = {element.get("name"): element.get("value") for element in shader.findall("input")}
        assert values["emission_color"] == "1, 0.5, 0"
        # standard_surface gates emission behind a weight defaulting to 0.
        assert float(values["emission"]) == 1.0

    def test_alpha_becomes_opacity_color3(self, bpy, tmp_path):
        add_material(bpy, "Glass", Alpha=0.35)

        result = export_materialx(str(tmp_path / "out.mtlx"))

        assert result["success"] is True
        shader = ET.parse(str(tmp_path / "out.mtlx")).getroot().find("standard_surface")
        values = {element.get("name"): element.get("value") for element in shader.findall("input")}
        assert values["opacity"] == "0.35, 0.35, 0.35"


class TestImportMaterialX:
    def test_imports_standard_surface(self, bpy, tmp_path):
        doc = write_document(_STANDARD_SURFACE_DOC, tmp_path / "copper.mtlx")

        result = import_materialx(str(doc))

        assert result["success"] is True
        assert result["context"]["material_count"] == 1
        material = bpy.data.materials.get("Copper")
        assert material is not None
        sockets = material.principled().inputs
        assert [round(value, 6) for value in sockets["Base Color"].default_value[:3]] == [0.72, 0.45, 0.2]
        assert sockets["Metallic"].default_value == 0.9
        assert sockets["Roughness"].default_value == 0.28
        assert sockets["IOR"].default_value == 1.6
        assert sockets["Coat Weight"].default_value == 0.4
        # `base` has no Principled counterpart and must be reported, not guessed.
        assert "base" in result["context"]["materials"][0]["unmapped_inputs"]

    def test_imports_open_pbr_surface(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <open_pbr_surface name="OPS_Plastic" type="surfaceshader">
    <input name="base_color" type="color3" value="0.1, 0.8, 0.3" />
    <input name="specular_roughness" type="float" value="0.15" />
    <input name="coat_weight" type="float" value="0.75" />
  </open_pbr_surface>
  <surfacematerial name="Plastic" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="OPS_Plastic" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "plastic.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True
        assert result["context"]["materials"][0]["source_node"] == "open_pbr_surface"
        sockets = bpy.data.materials.get("Plastic").principled().inputs
        assert [round(value, 6) for value in sockets["Base Color"].default_value[:3]] == [0.1, 0.8, 0.3]
        assert sockets["Roughness"].default_value == 0.15
        assert sockets["Coat Weight"].default_value == 0.75

    def test_imports_usd_preview_surface(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.38">
  <usd_preview_surface name="USD_Metal" type="surfaceshader">
    <input name="diffuseColor" type="color3" value="0.9, 0.1, 0.1" />
    <input name="metallic" type="float" value="1.0" />
    <input name="clearcoat" type="float" value="0.2" />
  </usd_preview_surface>
  <surfacematerial name="Metal" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="USD_Metal" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "metal.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True
        assert result["context"]["materials"][0]["source_node"] == "usd_preview_surface"
        sockets = bpy.data.materials.get("Metal").principled().inputs
        assert [round(value, 6) for value in sockets["Base Color"].default_value[:3]] == [0.9, 0.1, 0.1]
        assert sockets["Metallic"].default_value == 1.0
        assert sockets["Coat Weight"].default_value == 0.2

    def test_imports_shader_only_document(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="Bare" type="surfaceshader">
    <input name="metalness" type="float" value="0.25" />
  </standard_surface>
</materialx>
""",
            tmp_path / "bare.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True
        assert bpy.data.materials.get("Bare").principled().inputs["Metallic"].default_value == 0.25

    def test_connected_input_is_reported(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_Tex" type="surfaceshader">
    <input name="base_color" type="color3" nodename="image_1" />
    <input name="metalness" type="float" value="0.5" />
  </standard_surface>
  <surfacematerial name="Tex" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Tex" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "tex.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True
        entry = result["context"]["materials"][0]
        assert entry["connected_inputs"] == ["base_color"]
        assert "base_color" not in entry["applied"]
        assert any("base_color" in warning for warning in result["context"]["warnings"])

    def test_reuse_existing_updates_in_place(self, bpy, tmp_path):
        add_material(bpy, "Copper", Metallic=0.0)
        doc = write_document(_STANDARD_SURFACE_DOC, tmp_path / "copper.mtlx")

        result = import_materialx(str(doc))

        assert result["success"] is True
        assert result["context"]["materials"][0]["action"] == "updated"
        assert len(bpy.data.materials) == 1
        assert bpy.data.materials.get("Copper").principled().inputs["Metallic"].default_value == 0.9

    def test_reuse_existing_false_creates_a_copy(self, bpy, tmp_path):
        add_material(bpy, "Copper", Metallic=0.0)
        doc = write_document(_STANDARD_SURFACE_DOC, tmp_path / "copper.mtlx")

        result = import_materialx(str(doc), reuse_existing=False)

        assert result["success"] is True
        assert result["context"]["materials"][0]["action"] == "created"
        assert len(bpy.data.materials) == 2
        assert bpy.data.materials.get("Copper.001") is not None

    def test_filters_by_material_names(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_A" type="surfaceshader">
    <input name="metalness" type="float" value="0.1" />
  </standard_surface>
  <standard_surface name="SR_B" type="surfaceshader">
    <input name="metalness" type="float" value="0.2" />
  </standard_surface>
  <surfacematerial name="A" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_A" />
  </surfacematerial>
  <surfacematerial name="B" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_B" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "two.mtlx",
        )

        result = import_materialx(str(doc), material_names=["B"])

        assert result["success"] is True
        assert [item["material"] for item in result["context"]["materials"]] == ["B"]
        assert bpy.data.materials.get("A") is None

    def test_missing_material_fails(self, bpy, tmp_path):
        doc = write_document(_STANDARD_SURFACE_DOC, tmp_path / "copper.mtlx")

        result = import_materialx(str(doc), material_names=["Nope"])

        assert result["success"] is False
        assert "Nope" in result["error"]

    def test_invalid_xml_fails(self, bpy, tmp_path):
        doc = write_document("<materialx><standard_surface>", tmp_path / "broken.mtlx")

        result = import_materialx(str(doc))

        assert result["success"] is False
        assert "Invalid MaterialX document" in result["message"]

    def test_missing_file_fails(self, bpy, tmp_path):
        result = import_materialx(str(tmp_path / "absent.mtlx"))

        assert result["success"] is False

    def test_document_without_supported_shader_fails(self, bpy, tmp_path):
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <constant name="C" type="color3">
    <input name="value" type="color3" value="1, 1, 1" />
  </constant>
</materialx>
""",
            tmp_path / "constant.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is False
        assert "No MaterialX material found" in result["message"]


class TestRoundTrip:
    def test_values_survive_export_then_import(self, bpy, monkeypatch, tmp_path):
        add_material(
            bpy,
            "Copper",
            **{
                "Base Color": (0.72, 0.45, 0.2, 1.0),
                "Metallic": 0.94,
                "Roughness": 0.28,
                "IOR": 1.6,
                "Coat Weight": 0.4,
                "Sheen Weight": 0.15,
            },
        )
        out = tmp_path / "copper.mtlx"
        assert export_materialx(str(out))["success"] is True

        # Fresh scene: the imported material must not inherit the source object.
        fresh = FakeBpy()
        monkeypatch.setitem(sys.modules, "bpy", fresh)
        result = import_materialx(str(out))

        assert result["success"] is True
        sockets = fresh.data.materials.get("Copper").principled().inputs
        assert [round(value, 6) for value in sockets["Base Color"].default_value[:3]] == [0.72, 0.45, 0.2]
        assert sockets["Metallic"].default_value == 0.94
        assert sockets["Roughness"].default_value == 0.28
        assert sockets["IOR"].default_value == 1.6
        assert sockets["Coat Weight"].default_value == 0.4
        assert sockets["Sheen Weight"].default_value == 0.15


class TestStrictSocketImport:
    """Import against sockets that reject mismatched types like real bpy does.

    The plain FakeSocket accepts any assignment, so it cannot expose the
    demote-an-input path; these cases can.
    """

    _DOC = """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_Probe" type="surfaceshader">
    <input name="base_color" type="color3" value="0.2, 0.4, 0.6" />
    <input name="specular_color" type="color3" value="1.0, 0.5, 0.0" />
    <input name="metalness" type="float" value="0.75" />
  </standard_surface>
  <surfacematerial name="ProbeMat" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Probe" />
  </surfacematerial>
</materialx>
"""

    def test_mismatched_socket_demotes_only_that_input(self, bpy, tmp_path):
        """3.x Principled exposes Specular Tint as a float socket.

        A color3 value must demote to unmapped_inputs and leave the batch green,
        not fail the whole import.
        """
        material = bpy.data.materials.new("ProbeMat")
        material.use_nodes = True
        material.principled().inputs["Specular Tint"] = StrictSocket("Specular Tint", 0.5)
        doc = write_document(self._DOC, tmp_path / "probe.mtlx")

        result = import_materialx(str(doc))

        assert result["success"] is True, result.get("error")
        entry = result["context"]["materials"][0]
        assert "specular_color" in entry["unmapped_inputs"]
        # The compatible inputs on the same material still land.
        assert "Base Color" in entry["applied"]
        assert "Metallic" in entry["applied"]
        assert any("specular_color" in warning for warning in result["context"]["warnings"])

    def test_undersized_vector_demotes_only_that_input(self, bpy, tmp_path):
        material = bpy.data.materials.new("ProbeMat")
        material.use_nodes = True
        material.principled().inputs["Normal"] = StrictSocket("Normal", (0.0, 0.0, 0.0))
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_Probe" type="surfaceshader">
    <input name="normal" type="vector3" value="0.0, 1.0" />
    <input name="metalness" type="float" value="0.3" />
  </standard_surface>
  <surfacematerial name="ProbeMat" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Probe" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "probe.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True, result.get("error")
        entry = result["context"]["materials"][0]
        assert "normal" in entry["unmapped_inputs"]
        assert "Metallic" in entry["applied"]

    def test_one_bad_material_does_not_abort_the_batch(self, bpy, tmp_path):
        good = bpy.data.materials.new("Good")
        good.use_nodes = True
        bad = bpy.data.materials.new("Bad")
        bad.use_nodes = True
        bad.principled().inputs["Specular Tint"] = StrictSocket("Specular Tint", 0.5)
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_Good" type="surfaceshader">
    <input name="metalness" type="float" value="0.1" />
  </standard_surface>
  <standard_surface name="SR_Bad" type="surfaceshader">
    <input name="specular_color" type="color3" value="0.1, 0.2, 0.3" />
    <input name="metalness" type="float" value="0.9" />
  </standard_surface>
  <surfacematerial name="Good" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Good" />
  </surfacematerial>
  <surfacematerial name="Bad" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_Bad" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "two.mtlx",
        )

        result = import_materialx(str(doc))

        assert result["success"] is True, result.get("error")
        by_name = {item["material"]: item for item in result["context"]["materials"]}
        assert "specular_color" in by_name["Bad"]["unmapped_inputs"]
        assert by_name["Bad"]["applied"]["Metallic"] == 0.9
        assert by_name["Good"]["applied"]["Metallic"] == 0.1

    def test_interrupted_batch_reports_materials_already_created(self, bpy, tmp_path):
        """A failure mid-batch must say what is already in the scene."""
        doc = write_document(
            """<?xml version="1.0"?>
<materialx version="1.39">
  <standard_surface name="SR_A" type="surfaceshader">
    <input name="metalness" type="float" value="0.1" />
  </standard_surface>
  <standard_surface name="SR_B" type="surfaceshader">
    <input name="metalness" type="float" value="0.2" />
  </standard_surface>
  <surfacematerial name="A" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_A" />
  </surfacematerial>
  <surfacematerial name="B" type="material">
    <input name="surfaceshader" type="surfaceshader" nodename="SR_B" />
  </surfacematerial>
</materialx>
""",
            tmp_path / "two.mtlx",
        )
        original_new = bpy.data.materials.new
        calls = []

        def flaky(name):
            calls.append(name)
            if len(calls) > 1:
                raise RuntimeError("scene is locked")
            return original_new(name)

        bpy.data.materials.new = flaky

        result = import_materialx(str(doc))

        assert result["success"] is False
        assert result["context"]["created_materials"] == ["A"]
        assert bpy.data.materials.get("A") is not None
