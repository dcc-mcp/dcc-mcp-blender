"""Qualify typed numeric geometry and built-in text in a real Blender host."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import struct

import pytest

bpy = pytest.importorskip("bpy", reason="run inside the supported Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e

VERTICES = [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0], [0.5, 0.5, 1]]
FACES = [[0, 3, 2, 1], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
RINGS = [
    [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]],
    [[0.5, 0.25, 0], [0.5, 0.75, 0], [1.5, 0.75, 0], [1.5, 0.25, 0]],
]


def _point_hash(points):
    return hashlib.sha256(b"".join(struct.pack("<fff", *point) for point in points)).hexdigest()


def _topology_hash(faces):
    return hashlib.sha256(json.dumps(faces, separators=(",", ":")).encode("utf-8")).hexdigest()


def _call(stem, **kwargs):
    result = load_skill("blender-data-geometry", stem).main(**kwargs)
    assert result["success"] is True, result
    json.dumps(result, allow_nan=False)
    if stem == "create_text":
        assert result["postcondition"]["verified"] is True
        assert result["postcondition"]["method"] == "native_font_readback"
    return result["context"]


def _selection_state():
    active = bpy.context.view_layer.objects.active
    return (
        tuple(sorted(obj.name for obj in bpy.context.selected_objects)),
        active.name if active is not None else None,
        bpy.context.scene.frame_current,
        bpy.context.mode,
    )


def _native_state(name):
    obj = bpy.data.objects[name]
    data = obj.data
    state = {
        "type": obj.type,
        "data_name": data.name,
        "location": tuple(obj.location),
        "rotation": tuple(obj.rotation_euler),
        "scale": tuple(obj.scale),
        "matrix_world": tuple(tuple(row) for row in obj.matrix_world),
        "matrix_parent_inverse": tuple(tuple(row) for row in obj.matrix_parent_inverse),
        "parent": obj.parent.name if obj.parent is not None else None,
        "dimensions": tuple(obj.dimensions),
        "materials": tuple(material.name if material is not None else None for material in data.materials),
    }
    if obj.type == "MESH":
        state["positions"] = tuple(tuple(vertex.co) for vertex in data.vertices)
        state["faces"] = tuple(tuple(face.vertices) for face in data.polygons)
        state["position_hash"] = _point_hash(state["positions"])
        state["topology_hash"] = _topology_hash(state["faces"])
    elif obj.type == "CURVE":
        state["splines"] = tuple(
            (spline.type, spline.use_cyclic_u, tuple(tuple(point.co) for point in spline.points))
            for spline in data.splines
        )
        state["controls"] = (data.dimensions, data.extrude, data.bevel_depth, data.bevel_resolution)
        state["position_hash"] = _point_hash(point.co[:3] for spline in data.splines for point in spline.points)
    else:
        assert obj.type == "FONT"
        state["text"] = (data.body, data.size, data.extrude, data.align_x)
        state["font"] = (data.font.name, data.font.filepath, data.font.library)
    return state


def _host_state():
    bpy.context.view_layer.update()
    return (
        tuple(
            tuple((item.name, item.as_pointer(), item.users) for item in collection)
            for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.fonts)
        ),
        _selection_state(),
        tuple((obj.name, _native_state(obj.name)) for obj in bpy.data.objects),
    )


def _reject_without_mutation(stem, **kwargs):
    module = load_skill("blender-data-geometry", stem)
    before = _host_state()
    result = module.main(**kwargs)
    assert result["success"] is False, result
    assert _host_state() == before


@pytest.fixture(autouse=True)
def _owned_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(location=(-3, 0, 0))
    bpy.context.active_object.name = "SelectionAnchor"
    bpy.context.scene.frame_set(7)
    yield
    bpy.ops.wm.read_factory_settings(use_empty=True)


def test_mesh_and_poly_curve_native_buffers_and_inspection():
    selected = _selection_state()
    mesh = _call("create_mesh_from_data", name="NumericMesh", vertices=VERTICES, faces=FACES)
    assert _selection_state() == selected
    native_mesh = bpy.data.objects["NumericMesh"]
    assert [tuple(vertex.co) for vertex in native_mesh.data.vertices] == [tuple(point) for point in VERTICES]
    assert [tuple(face.vertices) for face in native_mesh.data.polygons] == [tuple(face) for face in FACES]
    assert (mesh["vertex_count"], mesh["edge_count"], mesh["face_count"]) == (5, 8, 5)
    assert mesh["position_float32_sha256"] == _point_hash(VERTICES)
    assert mesh["topology_sha256"] == _topology_hash(FACES)
    assert tuple(native_mesh.dimensions) == pytest.approx((2, 1, 1))

    paint = bpy.data.materials.new("NumericPaint")
    curve = _call(
        "create_curve_from_points",
        name="NumericContour",
        splines=RINGS,
        closed=True,
        dimensions="2D",
        extrude=0.125,
        material_name=paint.name,
    )
    assert _selection_state() == selected
    native_curve = bpy.data.objects["NumericContour"]
    assert native_curve.data.materials[0] == paint
    assert curve["spline_count"] == 2
    assert curve["control_point_count"] == 8
    assert curve["position_float32_sha256"] == _point_hash(point for ring in RINGS for point in ring)
    for spline, ring in zip(native_curve.data.splines, RINGS):
        assert spline.type == "POLY"
        assert spline.use_cyclic_u is True
        assert [tuple(point.co) for point in spline.points] == [tuple(point) + (1.0,) for point in ring]
    assert tuple(native_curve.dimensions) == pytest.approx((2, 1, 0.25))

    before = _host_state()
    for name, created in (("NumericMesh", mesh), ("NumericContour", curve)):
        inspected = _call("inspect_data_geometry", name=name)
        assert inspected["position_float32_sha256"] == created["position_float32_sha256"]
        state = _native_state(name)
        assert inspected["matrix_world"] == [list(row) for row in state["matrix_world"]]
        if state["type"] == "MESH":
            assert inspected["topology_sha256"] == state["topology_hash"]
        else:
            assert inspected["cyclic"] == [True, True]
            assert inspected["extrude_per_side"] == pytest.approx(0.125)
    assert _host_state() == before


@pytest.mark.parametrize("size,extrude,align_x", [(0.001, 0, "LEFT"), (0.2, 0.025, "CENTER"), (10, 0.1, "RIGHT")])
def test_builtin_text_native_formatting_and_boundary_readback(size, extrude, align_x):
    selected = _selection_state()
    paint = bpy.data.materials.new("TextPaint")
    body = "A-Z 09\nTyped title"
    created = _call(
        "create_text",
        name="NativeTitle",
        text=body,
        size=size,
        extrude=extrude,
        align_x=align_x,
        material_name=paint.name,
    )
    assert _selection_state() == selected
    obj = bpy.data.objects["NativeTitle"]
    bpy.context.view_layer.update()
    assert obj.type == "FONT"
    assert obj.data.body == body
    assert obj.data.size == pytest.approx(size)
    assert obj.data.extrude == pytest.approx(extrude)
    assert obj.data.align_x == align_x
    assert obj.data.font.filepath == "<builtin>"
    assert obj.data.font.library is None
    for slot in ("font", "font_bold", "font_italic", "font_bold_italic"):
        font = getattr(obj.data, slot)
        if font is not None:
            assert font.filepath == "<builtin>"
            assert font.library is None
    assert obj.data.materials[0] == paint
    assert obj.dimensions.x > 0 and obj.dimensions.y > 0
    assert obj.dimensions.z == pytest.approx(2 * extrude, abs=1e-6)
    assert created["font"] == obj.data.font.name
    before = _host_state()
    inspected = _call("inspect_text", name=obj.name)
    for key in ("text", "size", "extrude", "align_x", "font", "materials", "dimensions"):
        assert inspected[key] == created[key]
    assert _host_state() == before


def test_transformed_geometry_and_text_survive_save_and_relocated_reopen(tmp_path):
    _call("create_mesh_from_data", name="SavedMesh", vertices=VERTICES, faces=FACES)
    _call("create_curve_from_points", name="SavedContour", splines=RINGS, extrude=0.125)
    _call("create_text", name="SavedTitle", text="NATIVE\nDATA 01", size=0.5, extrude=0.025, align_x="CENTER")
    names = ("SavedMesh", "SavedContour", "SavedTitle")
    parent = bpy.data.objects["SelectionAnchor"]
    parent.rotation_euler = (0.125, 0.25, 0.375)
    parent.scale = (1.25, 0.75, 1.5)
    bpy.context.view_layer.update()
    for index, name in enumerate(names):
        moved = load_skill("blender-objects", "move_object").main(name=name, location=[index + 1.25, -2, 0.5])
        rotated = load_skill("blender-objects", "rotate_object").main(name=name, rotation=[15, 30, 45])
        scaled = load_skill("blender-objects", "scale_object").main(name=name, scale=[1.5, 0.75, 1.25])
        assert moved["success"] and rotated["success"] and scaled["success"], (moved, rotated, scaled)
        bpy.context.view_layer.update()
        world_before = tuple(tuple(row) for row in bpy.data.objects[name].matrix_world)
        parented = load_skill("blender-objects", "parent_object").main(child_name=name, parent_name=parent.name)
        assert parented["success"] is True, parented
        bpy.context.view_layer.update()
        for actual, expected in zip(bpy.data.objects[name].matrix_world, world_before):
            assert tuple(actual) == pytest.approx(expected, abs=1e-6)

    bpy.context.view_layer.update()
    before = {name: _native_state(name) for name in names}
    inspections = {
        name: _call("inspect_text" if name == "SavedTitle" else "inspect_data_geometry", name=name) for name in names
    }
    selected = _selection_state()
    source = tmp_path / "source" / "native-data.blend"
    relocated = tmp_path / "relocated" / "native-data.blend"
    source.parent.mkdir()
    relocated.parent.mkdir()
    saved = load_skill("blender-scene", "save_scene").main(filepath=str(source))
    assert saved["success"] is True, saved
    assert source.is_file() and source.stat().st_size > 0
    shutil.copyfile(str(source), str(relocated))
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(relocated.read_bytes()).digest()
    source.unlink()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert "SavedMesh" not in bpy.data.objects
    assert bpy.ops.wm.open_mainfile(filepath=str(relocated)) == {"FINISHED"}
    bpy.context.view_layer.update()
    assert _selection_state() == selected
    assert {name: _native_state(name) for name in names} == before
    for name in names:
        stem = "inspect_text" if name == "SavedTitle" else "inspect_data_geometry"
        assert _call(stem, name=name) == inspections[name]


@pytest.mark.parametrize(
    "vertices,faces",
    [
        ([[True, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]),
        ([[float("nan"), 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]),
        ([[1000001, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]),
        (VERTICES, [[0, 1, 5]]),
        (VERTICES, [[0, 1, 1]]),
        (VERTICES, [[0, 1, True]]),
        ([[0, 0, 0]] * 30001, [[0, 1, 2]]),
    ],
    ids=[
        "boolean-coordinate",
        "nonfinite",
        "coordinate-bound",
        "index-bound",
        "repeated-index",
        "boolean-index",
        "point-bound",
    ],
)
def test_mesh_rejections_leave_native_data_and_selection_untouched(vertices, faces):
    _reject_without_mutation("create_mesh_from_data", name="RejectedMesh", vertices=vertices, faces=faces)


@pytest.mark.parametrize(
    "changes",
    [
        {"splines": [[[0, 0, 0], [1, 0, 0]]]},
        {"splines": [[[0, 0, 0], [1, 0, 1], [0, 1, 0]]]},
        {"closed": 1},
        {"extrude": -0.001},
        {"bevel_resolution": 5},
        {"material_name": "MissingPaint"},
        {"splines": [RINGS[0]] * 1025},
    ],
    ids=[
        "closed-point-bound",
        "nonplanar-2d",
        "boolean-required",
        "negative-depth",
        "bevel-bound",
        "missing-material",
        "spline-bound",
    ],
)
def test_curve_rejections_leave_native_data_and_selection_untouched(changes):
    arguments = {"name": "RejectedCurve", "splines": RINGS}
    arguments.update(changes)
    _reject_without_mutation("create_curve_from_points", **arguments)


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "Title\x00"},
        {"text": "T\u00edtulo"},
        {"text": "A" * 161},
        {"text": "A\nB\nC\nD"},
        {"size": True},
        {"size": 10.001},
        {"extrude": 0.101},
        {"align_x": "JUSTIFY"},
        {"material_name": "MissingPaint"},
    ],
    ids=[
        "control-character",
        "non-ascii",
        "text-bound",
        "line-bound",
        "boolean-size",
        "size-bound",
        "depth-bound",
        "alignment",
        "missing-material",
    ],
)
def test_text_rejections_leave_native_data_and_selection_untouched(changes):
    arguments = {"name": "RejectedTitle", "text": "Typed title"}
    arguments.update(changes)
    _reject_without_mutation("create_text", **arguments)


def test_existing_object_and_orphan_data_names_are_preserved():
    mesh_args = {"name": "ExistingMesh", "vertices": VERTICES, "faces": FACES}
    curve_args = {"name": "ExistingCurve", "splines": RINGS}
    text_args = {"name": "ExistingTitle", "text": "Original text"}
    for stem, arguments in (
        ("create_mesh_from_data", mesh_args),
        ("create_curve_from_points", curve_args),
        ("create_text", text_args),
    ):
        _call(stem, **arguments)
        _reject_without_mutation(stem, **arguments)
        orphan_name = arguments["name"] + "DataOnly"
        if stem == "create_mesh_from_data":
            bpy.data.meshes.new(orphan_name)
        else:
            bpy.data.curves.new(orphan_name, type="FONT" if stem == "create_text" else "CURVE")
        orphan_arguments = dict(arguments, name=orphan_name)
        _reject_without_mutation(stem, **orphan_arguments)


@pytest.mark.parametrize(
    "stem,module_name,collection_name,arguments",
    [
        ("create_mesh_from_data", "_data_geometry", "meshes", {"vertices": VERTICES, "faces": FACES}),
        ("create_curve_from_points", "_data_geometry", "curves", {"splines": RINGS, "extrude": 0.125}),
        ("create_text", "_text_geometry", "curves", {"text": "Preserved text", "extrude": 0.025}),
    ],
    ids=["allocated-mesh", "allocated-poly-curve", "allocated-font"],
)
def test_interruption_after_native_allocation_cleans_only_owned_data(
    monkeypatch, stem, module_name, collection_name, arguments
):
    arguments = dict(arguments)
    if stem != "create_mesh_from_data":
        paint = bpy.data.materials.new("PreservedCancellationPaint")
        arguments["material_name"] = paint.name
    # Keep an existing result, and initialize Blender's shared built-in font
    # before taking the snapshot of data owned by this invocation.
    _call(stem, name="PreservedForCancellation", **arguments)
    module = importlib.import_module("dcc_mcp_blender." + module_name)
    collection = getattr(bpy.data, collection_name)
    name = "InterruptedNativeData"
    checkpoints = []
    selected = _selection_state()

    def interrupt_after_allocation():
        assert _selection_state() == selected
        assert bpy.data.objects.get(name) is None
        data = collection.get(name)
        if not checkpoints:
            assert data is None
            checkpoints.append("before-allocation")
            return
        assert checkpoints == ["before-allocation"]
        assert data is not None and data.users == 0
        if stem == "create_mesh_from_data":
            assert _point_hash(tuple(vertex.co) for vertex in data.vertices) == _point_hash(VERTICES)
            assert _topology_hash(tuple(tuple(face.vertices) for face in data.polygons)) == _topology_hash(FACES)
        elif stem == "create_curve_from_points":
            assert len(data.splines) == len(RINGS)
            assert _point_hash(point.co[:3] for spline in data.splines for point in spline.points) == _point_hash(
                point for ring in RINGS for point in ring
            )
        else:
            assert data.body == arguments["text"]
            assert data.font.filepath == "<builtin>" and data.font.library is None
        checkpoints.append("allocated")
        raise InterruptedError("synthetic cancellation after native readback")

    monkeypatch.setattr(module, "check_dcc_cancelled", interrupt_after_allocation)
    _reject_without_mutation(stem, name=name, **arguments)
    assert checkpoints == ["before-allocation", "allocated"]
    assert collection.get(name) is None
    assert bpy.data.objects.get(name) is None
