"""Unit tests for the typed Blender guide-curve grooming skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from tests.conftest import load_and_call


def _load_groom_ops_from_workspace():
    """Load the new helper from this checkout even with another editable install active."""
    module_name = "dcc_mcp_blender._groom_ops"
    module_path = Path(__file__).parents[1] / "src" / "dcc_mcp_blender" / "_groom_ops.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


_load_groom_ops_from_workspace()


class _NamedStore:
    def __init__(self):
        self.items = {}

    def get(self, name, default=None):
        return self.items.get(name, default)

    def __iter__(self):
        return iter(self.items.values())

    def __len__(self):
        return len(self.items)


class _Point:
    def __init__(self, co):
        self.co = tuple(co)
        self.radius = 1.0


class _Points(list):
    def add(self, count):
        self.extend(_Point((0.0, 0.0, 0.0, 1.0)) for _ in range(count))


class _Spline:
    def __init__(self):
        self.points = _Points([_Point((0.0, 0.0, 0.0, 1.0))])
        self.order_u = 0
        self.use_endpoint_u = False
        self.use_cyclic_u = False
        self.resolution_u = 0


class _Splines:
    def __init__(self):
        self.items = []

    def new(self, spline_type):
        assert spline_type == "NURBS"
        spline = _Spline()
        self.items.append(spline)
        return spline

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def remove(self, spline):
        self.items.remove(spline)


class _CurveData:
    def __init__(self, name):
        self.name = name
        self.splines = _Splines()
        self.materials = []
        self.users = 1
        self.bevel_depth = 0.0


class _CollectionObjects:
    def __init__(self):
        self.items = []

    def link(self, obj):
        if obj not in self.items:
            self.items.append(obj)

    def __iter__(self):
        return iter(self.items)

    def __contains__(self, value):
        return value in self.items or any(getattr(obj, "name", None) == value for obj in self.items)


class _Collection:
    def __init__(self, name):
        self.name = name
        self.objects = _CollectionObjects()
        self.children = _CollectionObjects()


class _Object:
    def __init__(self, name, object_type, data=None):
        self.name = name
        self.type = object_type
        self.data = data
        self.matrix_world = None
        self._props = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value


class _ObjectStore(_NamedStore):
    def new(self, name, data):
        object_type = "CURVE" if getattr(data, "type", "CURVE") == "CURVE" else "MESH"
        obj = _Object(name, object_type, data)
        self.items[name] = obj
        return obj

    def remove(self, obj, do_unlink=True):
        self.items.pop(obj.name, None)


class _CurveStore(_NamedStore):
    def new(self, name, type):
        data = _CurveData(name)
        data.type = type
        self.items[name] = data
        return data

    def remove(self, data):
        self.items.pop(data.name, None)


class _Material:
    def __init__(self, name):
        self.name = name
        self.use_nodes = False
        self.diffuse_color = None
        bsdf = SimpleNamespace(
            inputs={
                "Base Color": SimpleNamespace(default_value=None),
                "Roughness": SimpleNamespace(default_value=None),
            }
        )
        self.node_tree = SimpleNamespace(nodes={"Principled BSDF": bsdf})


class _MaterialStore(_NamedStore):
    def new(self, name):
        material = _Material(name)
        self.items[name] = material
        return material


def _bpy_fixture():
    objects = _ObjectStore()
    curves = _CurveStore()
    materials = _MaterialStore()
    collections = _NamedStore()
    root = _Collection("Scene Collection")
    collections.items[root.name] = root
    scene = SimpleNamespace(collection=root)
    context = SimpleNamespace(scene=scene, collection=None)
    data = SimpleNamespace(objects=objects, curves=curves, materials=materials, collections=collections)
    return SimpleNamespace(data=data, context=context), objects


def _add_scalp(objects):
    vertices = [
        SimpleNamespace(co=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)),
        SimpleNamespace(co=(1.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)),
        SimpleNamespace(co=(0.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0)),
    ]
    mesh = SimpleNamespace(vertices=vertices)
    scalp = _Object("Scalp", "MESH", mesh)
    objects.items[scalp.name] = scalp
    return scalp


def test_create_groom_guides_builds_curves_and_readback_metadata():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)

    result = load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=4,
        segments=3,
        length=1.0,
        seed=7,
        root_height_min=0.0,
    )

    assert result["success"] is True
    assert result["context"]["guide_count"] == 4
    assert result["context"]["point_count"] == 12
    groom = objects.get("Hair Groom")
    assert groom.type == "CURVE"
    assert groom.get("dcc_mcp_groom") == 1
    assert len(groom.data.splines) == 4
    assert len(groom.data.materials) == 1


def test_create_groom_guides_rejects_non_mesh_and_invalid_ranges():
    bpy, objects = _bpy_fixture()
    objects.items["Camera"] = _Object("Camera", "CAMERA")

    non_mesh = load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Camera",
    )
    invalid = load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Camera",
        guide_count=0,
    )

    assert non_mesh["success"] is False
    assert invalid["success"] is False


def test_set_groom_style_preserves_roots_and_scales_guides():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)
    created = load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=1,
        segments=3,
        length=2.0,
        curl=0.0,
    )
    assert created["success"] is True
    groom = objects.get("Hair Groom")
    points = groom.data.splines.items[0].points
    root = points[0].co
    endpoint_before = points[-1].co

    result = load_and_call(
        "blender-groom/scripts/set_groom_style.py",
        bpy,
        object_name="Hair Groom",
        length_scale=0.5,
        width=0.01,
        hair_color=[0.1, 0.05, 0.02, 1.0],
    )

    assert result["success"] is True
    assert points[0].co == root
    assert points[-1].co[0] == (root[0] + (endpoint_before[0] - root[0]) * 0.5)
    assert groom.data.bevel_depth == 0.01


def test_inspect_grooms_lists_only_generated_outputs():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)
    load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=2,
        segments=2,
    )

    result = load_and_call("blender-groom/scripts/inspect_grooms.py", bpy)

    assert result["success"] is True
    assert result["context"]["count"] == 1
    assert result["context"]["grooms"][0]["guide_count"] == 2
    assert result["context"]["grooms"][0]["parameters"]["guide_count"] == 2


def test_shape_groom_guides_preserves_roots_and_applies_taper():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)
    load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=1,
        segments=3,
        length=2.0,
        curl=0.0,
    )
    groom = objects.get("Hair Groom")
    points = groom.data.splines.items[0].points
    root = points[0].co

    result = load_and_call(
        "blender-groom/scripts/shape_groom_guides.py",
        bpy,
        object_name="Hair Groom",
        direction_bias=[1.0, 0.0, 0.0],
        taper=1.0,
    )

    assert result["success"] is True
    assert points[0].co == root
    assert points[0].radius == 1.0
    assert points[-1].radius == 0.01
    assert result["context"]["shape"]["direction_bias"] == [1.0, 0.0, 0.0]


def test_thin_duplicate_and_delete_groom_guides():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)
    load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=4,
        segments=2,
        root_height_min=0.0,
    )

    thinned = load_and_call(
        "blender-groom/scripts/thin_groom_guides.py",
        bpy,
        object_name="Hair Groom",
        density=0.5,
        seed=5,
    )
    assert thinned["success"] is True
    assert thinned["context"]["guide_count"] == 2

    duplicated = load_and_call(
        "blender-groom/scripts/duplicate_groom.py",
        bpy,
        object_name="Hair Groom",
        new_object_name="Hair Groom Variant",
    )
    assert duplicated["success"] is True
    assert objects.get("Hair Groom Variant").get("dcc_mcp_groom") == 1
    assert duplicated["context"]["guide_count"] == 2

    deleted = load_and_call(
        "blender-groom/scripts/delete_groom.py",
        bpy,
        object_name="Hair Groom Variant",
    )
    assert deleted["success"] is True
    assert objects.get("Hair Groom Variant") is None


def test_validate_groom_attachment_reports_root_distance():
    bpy, objects = _bpy_fixture()
    _add_scalp(objects)
    load_and_call(
        "blender-groom/scripts/create_groom_guides.py",
        bpy,
        scalp_object_name="Scalp",
        groom_name="Hair Groom",
        guide_count=2,
        segments=2,
        root_height_min=0.0,
    )

    attached = load_and_call(
        "blender-groom/scripts/validate_groom_attachment.py",
        bpy,
        object_name="Hair Groom",
        tolerance=0.001,
    )
    assert attached["success"] is True
    assert attached["context"]["valid"] is True
    assert attached["context"]["detached_root_count"] == 0

    groom = objects.get("Hair Groom")
    groom.data.splines.items[0].points[0].co = (10.0, 10.0, 10.0, 1.0)
    detached = load_and_call(
        "blender-groom/scripts/validate_groom_attachment.py",
        bpy,
        object_name="Hair Groom",
        tolerance=0.001,
    )
    assert detached["context"]["valid"] is False
    assert detached["context"]["detached_root_count"] == 1
