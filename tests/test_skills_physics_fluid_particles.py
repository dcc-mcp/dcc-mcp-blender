"""Unit tests for the Mantaflow, Dynamic Paint, and particle tools (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from tests.conftest import load_and_call
from tests.test_skills_physics import _bpy_with_objects, _make_obj

PHYSICS_PATH = "src/dcc_mcp_blender/skills/blender-physics/tools.yaml"
SKILL = "blender-physics"


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL}/scripts/{script}.py", bpy, **kwargs)


def _domain_settings():
    return SimpleNamespace(
        resolution_divisions=32,
        viscosity_base=0.0,
        domain_size=1.0,
        time_scale=1.0,
        use_noise=False,
    )


def _canvas_settings():
    return SimpleNamespace(
        canvas_surfaces=[],
        paint_wetness=1.0,
        paint_dry_speed=0.5,
    )


def _brush_settings():
    return SimpleNamespace(
        brush_alpha=1.0,
        brush_radius=0.5,
        brush_smudge_strength=0.0,
    )


def _hair_knobs(settings):
    """Add the hair/children/instance properties the new tools target.

    The shared physics fixture only models the emitter knobs that
    add_particle_system already used, so tests that exercise hair, children,
    or instancing have to opt in.
    """
    settings.type = "EMITTER"
    settings.child_type = "NONE"
    settings.child_nbr = 0
    settings.rendered_child_count = 0
    settings.hair_length = 4.0
    settings.hair_step = 2
    settings.particle_size = 0.05
    settings.use_render_emitter = True
    return settings


def _obj_with_particle_system(name="Cube", system_name="ParticleSystem"):
    obj = _make_obj(name)
    modifier = obj.modifiers.new(system_name, "PARTICLE_SYSTEM")
    _hair_knobs(modifier.particle_system.settings)
    return obj


def _bpy_with_temp_override(*objects):
    """Return (bpy, calls) where the ptcache operator calls are recorded."""
    bpy = _bpy_with_objects(*objects)
    calls: list = []

    class _TempOverride:
        def __init__(self, **override):
            self.override = override

        def __enter__(self):
            return self.override

        def __exit__(self, *exc):
            return False

    bpy.context.temp_override = lambda **override: _TempOverride(**override)
    bpy.ops.ptcache.bake = lambda **kwargs: calls.append(("bake", kwargs))
    bpy.ops.ptcache.free_bake = lambda: calls.append(("free_bake", {}))
    return bpy, calls


# ---------------------------------------------------------------------------
# Mantaflow fluid
# ---------------------------------------------------------------------------


def test_add_fluid_modifier_creates_a_domain():
    obj = _make_obj()
    result = _call("add_fluid_modifier", _bpy_with_objects(obj), object_name="Cube", fluid_type="domain")

    assert result["success"] is True
    modifier = obj.modifiers.get("Fluid Domain")
    assert modifier is not None
    assert modifier.type == "FLUID"
    assert modifier.fluid_type == "DOMAIN"
    assert result["context"]["fluid_type"] == "DOMAIN"


def test_add_fluid_modifier_accepts_flow_and_effector():
    obj = _make_obj()
    bpy = _bpy_with_objects(obj)
    _call("add_fluid_modifier", bpy, object_name="Cube", fluid_type="flow", name="Inflow")
    _call("add_fluid_modifier", bpy, object_name="Cube", fluid_type="effector", name="Stir")

    assert obj.modifiers.get("Inflow").fluid_type == "FLOW"
    assert obj.modifiers.get("Stir").fluid_type == "EFFECTOR"


def test_add_fluid_modifier_rejects_unknown_type():
    obj = _make_obj()
    result = _call("add_fluid_modifier", _bpy_with_objects(obj), object_name="Cube", fluid_type="LAVA")
    assert result["success"] is False
    assert "unsupported fluid type" in result["message"].lower()


def test_add_fluid_modifier_rejects_non_mesh():
    obj = _make_obj()
    obj.type = "CAMERA"
    result = _call("add_fluid_modifier", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is False
    assert "not a mesh" in result["message"].lower()


def test_set_fluid_settings_writes_domain_settings():
    obj = _make_obj()
    modifier = obj.modifiers.new("Fluid Domain", "FLUID")
    modifier.fluid_type = "DOMAIN"
    modifier.domain_settings = _domain_settings()

    result = _call(
        "set_fluid_settings",
        _bpy_with_objects(obj),
        object_name="Cube",
        domain_settings={"resolution_divisions": 96, "viscosity_base": 0.5},
    )
    assert result["success"] is True
    assert modifier.domain_settings.resolution_divisions == 96
    assert modifier.domain_settings.viscosity_base == 0.5
    assert result["context"]["domain_applied"]["resolution_divisions"] == 96


def test_set_fluid_settings_without_a_domain_reports_missing_block():
    obj = _make_obj()
    modifier = obj.modifiers.new("Fluid Flow", "FLUID")
    modifier.fluid_type = "FLOW"
    modifier.domain_settings = None

    result = _call(
        "set_fluid_settings",
        _bpy_with_objects(obj),
        object_name="Cube",
        domain_settings={"resolution_divisions": 64},
    )
    assert result["success"] is False
    assert "domain settings unavailable" in result["message"].lower()


def test_set_fluid_settings_requires_a_change():
    obj = _make_obj()
    obj.modifiers.new("Fluid Domain", "FLUID")
    result = _call("set_fluid_settings", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is False
    assert "no fluid settings" in result["message"].lower()


# ---------------------------------------------------------------------------
# Dynamic Paint
# ---------------------------------------------------------------------------


def test_add_dynamic_paint_modifier_creates_a_canvas():
    obj = _make_obj()
    result = _call("add_dynamic_paint_modifier", _bpy_with_objects(obj), object_name="Cube")

    assert result["success"] is True
    modifier = obj.modifiers.get("Dynamic Paint Canvas")
    assert modifier.type == "DYNAMIC_PAINT"
    assert modifier.ui_type == "CANVAS"
    assert result["context"]["paint_type"] == "CANVAS"


def test_add_dynamic_paint_modifier_creates_a_brush():
    obj = _make_obj()
    result = _call("add_dynamic_paint_modifier", _bpy_with_objects(obj), object_name="Cube", paint_type="brush")

    assert result["success"] is True
    assert obj.modifiers.get("Dynamic Paint Brush").ui_type == "BRUSH"
    assert result["context"]["paint_type"] == "BRUSH"


def test_add_dynamic_paint_modifier_rejects_unknown_type():
    obj = _make_obj()
    result = _call("add_dynamic_paint_modifier", _bpy_with_objects(obj), object_name="Cube", paint_type="SPRAY")
    assert result["success"] is False
    assert "unsupported dynamic paint type" in result["message"].lower()


def test_set_dynamic_paint_settings_targets_the_canvas_block():
    obj = _make_obj()
    modifier = obj.modifiers.new("Canvas", "DYNAMIC_PAINT")
    modifier.ui_type = "CANVAS"
    modifier.canvas_settings = _canvas_settings()
    modifier.brush_settings = None

    result = _call(
        "set_dynamic_paint_settings",
        _bpy_with_objects(obj),
        object_name="Cube",
        settings={"paint_dry_speed": 0.75},
    )
    assert result["success"] is True
    assert modifier.canvas_settings.paint_dry_speed == 0.75
    assert result["context"]["paint_type"] == "CANVAS"


def test_set_dynamic_paint_settings_targets_the_brush_block():
    obj = _make_obj()
    modifier = obj.modifiers.new("Brush", "DYNAMIC_PAINT")
    modifier.ui_type = "BRUSH"
    modifier.brush_settings = _brush_settings()
    modifier.canvas_settings = None

    result = _call(
        "set_dynamic_paint_settings",
        _bpy_with_objects(obj),
        object_name="Cube",
        settings={"brush_alpha": 0.4},
    )
    assert result["success"] is True
    assert modifier.brush_settings.brush_alpha == 0.4
    assert result["context"]["paint_type"] == "BRUSH"


class _SurfaceCollection(list):
    def get(self, name):
        for surface in self:
            if getattr(surface, "name", None) == name:
                return surface
        return None

    def new(self, *args):
        surface = SimpleNamespace(name="Surface", surface_type="PAINT", is_active=True)
        self.append(surface)
        return surface


def test_add_dynamic_paint_surface_appends_to_the_canvas():
    obj = _make_obj()
    modifier = obj.modifiers.new("Canvas", "DYNAMIC_PAINT")
    modifier.ui_type = "CANVAS"
    modifier.canvas_settings = _canvas_settings()
    modifier.canvas_settings.canvas_surfaces = _SurfaceCollection()

    result = _call(
        "add_dynamic_paint_surface",
        _bpy_with_objects(obj),
        object_name="Cube",
        surface_type="weight",
        name="Wetmap",
    )
    assert result["success"] is True
    surfaces = modifier.canvas_settings.canvas_surfaces
    assert len(surfaces) == 1
    assert surfaces.get("Wetmap").surface_type == "WEIGHT"
    assert result["context"]["created"] is True


def test_add_dynamic_paint_surface_rejects_unknown_surface():
    obj = _make_obj()
    modifier = obj.modifiers.new("Canvas", "DYNAMIC_PAINT")
    modifier.ui_type = "CANVAS"
    modifier.canvas_settings = _canvas_settings()
    modifier.canvas_settings.canvas_surfaces = _SurfaceCollection()

    result = _call("add_dynamic_paint_surface", _bpy_with_objects(obj), object_name="Cube", surface_type="SPLASH")
    assert result["success"] is False
    assert "unsupported dynamic paint surface" in result["message"].lower()


def test_add_dynamic_paint_surface_rejects_a_brush_modifier():
    obj = _make_obj()
    modifier = obj.modifiers.new("Brush", "DYNAMIC_PAINT")
    modifier.ui_type = "BRUSH"
    modifier.canvas_settings = _canvas_settings()
    modifier.canvas_settings.canvas_surfaces = _SurfaceCollection()

    result = _call("add_dynamic_paint_surface", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is False
    assert "not a dynamic paint canvas" in result["message"].lower()


def test_list_dynamic_paint_surfaces_only_reports_canvases():
    obj = _make_obj()
    canvas = obj.modifiers.new("Canvas", "DYNAMIC_PAINT")
    canvas.ui_type = "CANVAS"
    canvas.canvas_settings = _canvas_settings()
    canvas.canvas_settings.canvas_surfaces = _SurfaceCollection()
    canvas.canvas_settings.canvas_surfaces.new()
    canvas.canvas_settings.canvas_surfaces[0].name = "Wetmap"
    brush = obj.modifiers.new("Brush", "DYNAMIC_PAINT")
    brush.ui_type = "BRUSH"
    brush.canvas_settings = _canvas_settings()
    brush.canvas_settings.canvas_surfaces = _SurfaceCollection()
    brush.canvas_settings.canvas_surfaces.new()

    result = _call("list_dynamic_paint_surfaces", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is True
    assert result["context"]["count"] == 1
    assert result["context"]["surfaces"][0]["name"] == "Wetmap"
    assert result["context"]["surfaces"][0]["modifier_name"] == "Canvas"


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------


def test_set_particle_hair_switches_to_hair_and_back():
    obj = _obj_with_particle_system()
    bpy = _bpy_with_objects(obj)

    result = _call("set_particle_hair", bpy, object_name="Cube", enabled=True, settings={"hair_length": 2.5})
    assert result["success"] is True
    assert obj.modifiers[0].particle_system.settings.type == "HAIR"
    assert obj.modifiers[0].particle_system.settings.hair_length == 2.5
    assert result["context"]["type"] == "HAIR"

    result = _call("set_particle_hair", bpy, object_name="Cube", enabled=False)
    assert result["success"] is True
    assert obj.modifiers[0].particle_system.settings.type == "EMITTER"
    assert result["context"]["type"] == "EMITTER"


def test_set_particle_hair_resolves_a_named_system():
    obj = _obj_with_particle_system(system_name="Fur")
    bpy = _bpy_with_objects(obj)
    _call("add_particle_system", bpy, object_name="Cube", name="Sparks")
    _hair_knobs(obj.modifiers.get("Sparks").particle_system.settings)

    result = _call("set_particle_hair", bpy, object_name="Cube", system_name="Sparks")
    assert result["success"] is True
    assert obj.modifiers.get("Fur").particle_system.settings.type == "EMITTER"
    assert obj.modifiers.get("Sparks").particle_system.settings.type == "HAIR"
    assert result["context"]["system_name"] == "Sparks"


def test_set_particle_hair_reports_a_missing_system():
    obj = _make_obj()
    result = _call("set_particle_hair", _bpy_with_objects(obj), object_name="Cube", system_name="Ghost")
    assert result["success"] is False
    assert "particle system not found" in result["message"].lower()


def test_set_particle_children_sets_type_and_counts():
    obj = _obj_with_particle_system()
    result = _call(
        "set_particle_children",
        _bpy_with_objects(obj),
        object_name="Cube",
        child_type="interpolated",
        child_nbr=20,
        rendered_child_count=80,
    )

    assert result["success"] is True
    settings = obj.modifiers[0].particle_system.settings
    assert settings.child_type == "INTERPOLATED"
    assert settings.child_nbr == 20
    assert settings.rendered_child_count == 80


def test_set_particle_children_rejects_unknown_type_and_range():
    obj = _obj_with_particle_system()
    bpy = _bpy_with_objects(obj)

    result = _call("set_particle_children", bpy, object_name="Cube", child_type="CLONED")
    assert result["success"] is False
    assert "unsupported child type" in result["message"].lower()

    result = _call("set_particle_children", bpy, object_name="Cube", child_nbr=20000)
    assert result["success"] is False
    assert "child_nbr" in result["error"].lower()

    result = _call("set_particle_children", bpy, object_name="Cube", rendered_child_count=-1)
    assert result["success"] is False
    assert "rendered child count" in result["message"].lower()


def test_set_particle_children_reports_missing_properties_as_skipped():
    obj = _obj_with_particle_system()
    del obj.modifiers[0].particle_system.settings.child_type

    result = _call("set_particle_children", _bpy_with_objects(obj), object_name="Cube", child_type="SIMPLE")
    assert result["success"] is True
    assert "child_type" in result["context"]["skipped"]


def test_set_particle_instance_assigns_the_object_and_render_type():
    obj = _obj_with_particle_system()
    source = _make_obj("Leaf")

    result = _call(
        "set_particle_instance",
        _bpy_with_objects(obj, source),
        object_name="Cube",
        instance_object_name="Leaf",
        show_emitter=False,
        particle_size=0.25,
    )
    assert result["success"] is True
    settings = obj.modifiers[0].particle_system.settings
    assert settings.instance_object is source
    assert settings.render_type == "OBJECT"
    assert settings.particle_size == 0.25
    assert result["context"]["applied"]["show_emitter"] is False


def test_set_particle_instance_reports_an_unknown_instance_object():
    obj = _obj_with_particle_system()
    result = _call(
        "set_particle_instance",
        _bpy_with_objects(obj),
        object_name="Cube",
        instance_object_name="Ghost",
    )
    assert result["success"] is False
    assert "object not found" in result["message"].lower()


def test_set_particle_instance_requires_a_change():
    obj = _obj_with_particle_system()
    result = _call("set_particle_instance", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is False
    assert "no instance settings" in result["message"].lower()


def test_bake_particle_system_bakes_the_system_cache():
    obj = _obj_with_particle_system()
    bpy, calls = _bpy_with_temp_override(obj)

    result = _call("bake_particle_system", bpy, object_name="Cube", frame_start=1, frame_end=120)
    assert result["success"] is True
    assert calls == [("bake", {"bake": True})]
    cache = obj.modifiers[0].particle_system.point_cache
    assert cache.frame_end == 120
    assert result["context"]["cache"]["frame_end"] == 120


def test_bake_particle_system_can_free_the_cache():
    obj = _obj_with_particle_system()
    bpy, calls = _bpy_with_temp_override(obj)

    result = _call("bake_particle_system", bpy, object_name="Cube", free=True)
    assert result["success"] is True
    assert calls == [("free_bake", {})]
    assert result["context"]["freed"] is True


def test_bake_particle_system_reports_a_missing_system():
    obj = _make_obj()
    result = _call("bake_particle_system", _bpy_with_objects(obj), object_name="Cube", system_name="Ghost")
    assert result["success"] is False
    assert "particle system not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_the_new_tools():
    doc = yaml.safe_load(Path(PHYSICS_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "add_fluid_modifier",
        "set_fluid_settings",
        "add_dynamic_paint_modifier",
        "set_dynamic_paint_settings",
        "add_dynamic_paint_surface",
        "list_dynamic_paint_surfaces",
        "set_particle_hair",
        "set_particle_children",
        "set_particle_instance",
        "bake_particle_system",
    }.issubset(tools)


def test_new_tools_declare_required_contract_fields():
    doc = yaml.safe_load(Path(PHYSICS_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    for name in (
        "add_fluid_modifier",
        "set_fluid_settings",
        "add_dynamic_paint_modifier",
        "set_dynamic_paint_settings",
        "add_dynamic_paint_surface",
        "list_dynamic_paint_surfaces",
        "set_particle_hair",
        "set_particle_children",
        "set_particle_instance",
        "bake_particle_system",
    ):
        tool = tools[name]
        assert tool["execution"] == "sync", name
        assert tool["affinity"] == "main", name
        source = Path("src/dcc_mcp_blender/skills") / SKILL / tool["source_file"]
        assert source.is_file(), f"missing source script: {source}"


def test_only_read_only_tools_are_flagged_read_only():
    doc = yaml.safe_load(Path(PHYSICS_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert tools["list_dynamic_paint_surfaces"]["read_only"] is True
    assert tools["list_dynamic_paint_surfaces"]["annotations"]["read_only_hint"] is True
    for name in ("add_fluid_modifier", "set_particle_hair", "bake_particle_system"):
        assert tools[name]["read_only"] is False
        assert tools[name]["annotations"]["read_only_hint"] is False
