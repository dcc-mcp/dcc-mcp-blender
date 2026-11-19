"""Contract tests for photographic post and delivery skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

import dcc_mcp_blender._photographic_validation_ops as validation_ops
from dcc_mcp_blender._photographic_delivery_ops import (
    VIDEO_COLOR_SPACE,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_PIXEL_FORMAT,
    _sequence_pattern,
    encode_photographic_video,
)
from dcc_mcp_blender._photographic_post_ops import (
    DEFAULT_HALATION_THRESHOLD,
    _curve_points,
    _grain_pixels,
    _prompt_default_issues,
    _values_equal,
    configure_photographic_post,
)
from dcc_mcp_blender._photographic_validation_ops import _validate_surface, validate_photographic_shot


class _ObjectCollection(dict):
    def __iter__(self):
        return iter(self.values())


def _fake_shot_bpy():
    focus = SimpleNamespace(name="Eyes", type="EMPTY")
    camera_data = SimpleNamespace(
        lens=50.0,
        sensor_width=36.0,
        dof=SimpleNamespace(
            use_dof=True,
            aperture_fstop=4.0,
            aperture_blades=0,
            focus_object=focus,
        ),
    )
    camera = SimpleNamespace(
        name="Camera",
        type="CAMERA",
        data=camera_data,
        location=[0.0, 0.0, 0.02],
        animation_data=None,
    )
    material = SimpleNamespace(
        name="Surface",
        use_nodes=True,
        node_tree=SimpleNamespace(nodes=[]),
    )

    def mesh(name, dimensions):
        return SimpleNamespace(
            name=name,
            type="MESH",
            dimensions=dimensions,
            modifiers=[],
            material_slots=[SimpleNamespace(material=material)],
            data=SimpleNamespace(materials=[material]),
            animation_data=None,
        )

    objects = _ObjectCollection(
        {
            "Camera": camera,
            "Eyes": focus,
            "Hero": mesh("Hero", (0.05, 0.05, 0.05)),
            "Background": mesh("Background", (2.0, 2.0, 2.0)),
            "Floor": mesh("Floor", (2.0, 2.0, 0.02)),
            "Wall": mesh("Wall", (2.0, 0.02, 2.0)),
            "Key": SimpleNamespace(name="Key", type="LIGHT", data=SimpleNamespace(type="AREA", energy=100.0)),
        }
    )
    scene = SimpleNamespace(
        name="Scene",
        camera=camera,
        frame_start=1,
        frame_end=2,
        unit_settings=SimpleNamespace(system="METRIC", scale_length=1.0, length_unit="METERS"),
        cycles=SimpleNamespace(samples=64, device="GPU"),
    )
    return SimpleNamespace(
        context=SimpleNamespace(scene=scene),
        data=SimpleNamespace(objects=objects, scenes={"Scene": scene}),
    )


def _pbr_material(texture_source="Poly Haven"):
    coordinate_node = SimpleNamespace(type="TEX_COORD")
    object_socket = SimpleNamespace(name="Object")
    textures = {}
    for map_name in ("diffuse", "roughness", "normal"):
        vector_socket = SimpleNamespace(
            name="Vector",
            links=[SimpleNamespace(from_node=coordinate_node, from_socket=object_socket)],
        )
        textures[map_name] = SimpleNamespace(
            name=f"DCC Photo {map_name.title()} Texture",
            type="TEX_IMAGE",
            bl_idname="ShaderNodeTexImage",
            inputs=[vector_socket],
            outputs=[SimpleNamespace(name="Color")],
            image=SimpleNamespace(channels=4),
            projection="BOX",
            projection_blend=0.25,
        )

    normal_color = SimpleNamespace(name="Color", links=[])
    normal_output = SimpleNamespace(name="Normal")
    normal_map = SimpleNamespace(
        name="DCC Photo Normal Map",
        type="NORMAL_MAP",
        inputs=[normal_color],
        outputs=[normal_output],
    )
    diffuse_output = textures["diffuse"].outputs[0]
    roughness_output = textures["roughness"].outputs[0]
    normal_image_output = textures["normal"].outputs[0]
    normal_color.links.append(SimpleNamespace(from_node=textures["normal"], from_socket=normal_image_output))
    base_color = SimpleNamespace(name="Base Color", links=[])
    roughness = SimpleNamespace(name="Roughness", links=[])
    normal = SimpleNamespace(name="Normal", links=[])
    base_color.links.append(SimpleNamespace(from_node=textures["diffuse"], from_socket=diffuse_output))
    roughness.links.append(SimpleNamespace(from_node=textures["roughness"], from_socket=roughness_output))
    normal.links.append(SimpleNamespace(from_node=normal_map, from_socket=normal_output))
    principled = SimpleNamespace(
        name="Principled BSDF",
        type="BSDF_PRINCIPLED",
        inputs=[base_color, roughness, normal],
    )
    return SimpleNamespace(
        name="Floor Scan",
        use_nodes=True,
        dcc_mcp_photographic_texture_source=texture_source,
        dcc_mcp_photographic_normal_map_convention="OPENGL",
        node_tree=SimpleNamespace(nodes=[principled, normal_map, *textures.values()]),
    )


def test_photographic_post_defaults_and_grain_are_frame_deterministic():
    assert DEFAULT_HALATION_THRESHOLD == 185.0 / 255.0
    assert _grain_pixels(2, 1337, 1) == _grain_pixels(2, 1337, 1)
    assert _grain_pixels(2, 1337, 1) != _grain_pixels(2, 1337, 2)


def test_photographic_post_validation_helpers_compare_color_sequences_and_curve_points():
    point_a = SimpleNamespace(location=(0.25, 0.18))
    point_b = SimpleNamespace(location=(0.75, 0.82))
    node = SimpleNamespace(mapping=SimpleNamespace(curves=[SimpleNamespace(points=[point_a, point_b])]))

    assert _values_equal([1.0, 0.82, 0.62], (1.0, 0.82, 0.62))
    assert _curve_points(node) == [[0.25, 0.18], [0.75, 0.82]]


def test_photographic_post_prompt_defaults_are_machine_checked():
    assert (
        _prompt_default_issues(
            {
                "halation_threshold": 185.0 / 255.0,
                "halation_tint": [1.0, 0.82, 0.62],
                "halation_mix": 0.34,
                "vignette_strength": 0.2,
                "s_curve_points": [[0.25, 0.18], [0.75, 0.82]],
            }
        )
        == []
    )

    issues = _prompt_default_issues(
        {
            "halation_threshold": 185.0 / 255.0,
            "halation_tint": [1.0, 0.82, 0.62],
            "halation_mix": 0.25,
            "vignette_strength": 0.2,
            "s_curve_points": [[0.25, 0.18], [0.75, 0.82]],
        }
    )
    assert issues[0]["code"] == "PHOTO_POST_PROMPT_DEFAULT_MISMATCH"
    assert issues[0]["field"] == "halation_mix"


def test_photographic_post_rejects_invalid_grain_size_without_blender():
    result = configure_photographic_post(grain_size=8)

    assert result["success"] is False
    assert "grain_size" in result["error"]


def test_delivery_contract_and_sequence_pattern():
    assert (VIDEO_FPS, VIDEO_CRF, VIDEO_PIXEL_FORMAT, VIDEO_COLOR_SPACE) == (24, 15, "yuv420p", "bt709")
    assert _sequence_pattern("C:/renders/toy_####.jpg") == "C:/renders/toy_%04d.jpg"
    assert _sequence_pattern("C:/renders/toy_%04d.jpg") == "C:/renders/toy_%04d.jpg"


def test_delivery_rejects_reversed_frame_range():
    result = encode_photographic_video("frames_####.jpg", "movie.mp4", 10, 1)

    assert result["success"] is False
    assert "end_frame" in result["error"]


def test_tools_yaml_declares_photographic_contracts():
    root = Path("src/dcc_mcp_blender/skills")
    post = yaml.safe_load((root / "blender-photographic-post/tools.yaml").read_text(encoding="utf-8"))
    delivery = yaml.safe_load((root / "blender-photographic-delivery/tools.yaml").read_text(encoding="utf-8"))
    validation = yaml.safe_load((root / "blender-validation/tools.yaml").read_text(encoding="utf-8"))
    render_profile = yaml.safe_load((root / "blender-render-profile/tools.yaml").read_text(encoding="utf-8"))

    assert {tool["name"] for tool in post["tools"]} == {
        "configure_photographic_post",
        "validate_photographic_post",
    }
    assert {tool["name"] for tool in delivery["tools"]} == {
        "configure_photographic_video_output",
        "validate_photographic_video_output",
        "encode_photographic_video",
    }
    photographic_validation = next(tool for tool in validation["tools"] if tool["name"] == "validate_photographic_shot")
    assert set(photographic_validation["input_schema"]["required"]) == {
        "hero_object",
        "focus_object",
        "background_object",
        "floor_object",
        "wall_object",
        "source_name",
    }
    properties = photographic_validation["input_schema"]["properties"]
    assert properties["scene_kind"]["enum"] == ["EXTERIOR", "INTERIOR"]
    assert properties["toy_object_names"]["items"]["type"] == "string"
    assert properties["minimum_environment_dimension_m"]["default"] == 1.0
    assert "preview_still_path" in properties
    assert properties["require_preview_still"]["default"] is True
    assert properties["require_pbr_textures"]["default"] is True
    assert "render_photographic_test_still" in {tool["name"] for tool in render_profile["tools"]}
    post_validate = next(tool for tool in post["tools"] if tool["name"] == "validate_photographic_post")
    assert post_validate["input_schema"]["properties"]["require_prompt_defaults"]["default"] is True


def test_complete_surface_validation_requires_polyhaven_pbr_maps():
    material = _pbr_material("Local file")
    surface = SimpleNamespace(
        name="Floor",
        type="MESH",
        dimensions=(2.0, 2.0, 0.02),
        material_slots=[SimpleNamespace(material=material)],
    )

    issues = []
    state = _validate_surface(surface, "floor", issues, 1.0, True)

    assert state["pbr"]["valid"] is False
    assert any(issue["code"] == "PHOTO_SURFACE_PBR" for issue in issues)

    material.dcc_mcp_photographic_texture_source = "Poly Haven"
    issues = []
    state = _validate_surface(surface, "floor", issues, 1.0, True)

    assert state["pbr"]["valid"] is True
    assert issues == []


def test_complete_surface_validation_requires_opengl_normals_and_connected_maps():
    material = _pbr_material("Poly Haven")
    surface = SimpleNamespace(
        name="Floor",
        type="MESH",
        dimensions=(2.0, 2.0, 0.02),
        material_slots=[SimpleNamespace(material=material)],
    )

    material.dcc_mcp_photographic_normal_map_convention = "DIRECTX"
    issues = []
    state = _validate_surface(surface, "floor", issues, 1.0, True)

    assert state["pbr"]["valid"] is False
    assert any(issue["code"] == "PHOTO_SURFACE_PBR" for issue in issues)

    material.dcc_mcp_photographic_normal_map_convention = "OPENGL"
    material.node_tree.nodes[0].inputs[0].links = []
    issues = []
    state = _validate_surface(surface, "floor", issues, 1.0, True)

    assert state["pbr"]["valid"] is False
    assert state["pbr"]["materials"][0]["links"]["diffuse"] is False


def test_complete_shot_validation_rejects_cpu_backend(monkeypatch):
    fake_bpy = _fake_shot_bpy()
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    monkeypatch.setattr(
        validation_ops,
        "validate_render_profile",
        lambda **kwargs: {
            "success": True,
            "context": {"valid": True, "resolved_device_backend": "CPU"},
        },
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_photographic_post",
        lambda **kwargs: {"success": True, "context": {"valid": True}},
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_motivated_lighting",
        lambda **kwargs: {"success": True, "context": {"valid": True}},
    )

    result = validate_photographic_shot(
        hero_object="Hero",
        focus_object="Eyes",
        background_object="Background",
        floor_object="Floor",
        wall_object="Wall",
        source_name="Key",
        preview_still_path="preview.jpg",
    )

    assert any(issue["code"] == "PHOTO_GPU_BACKEND" for issue in result["context"]["issues"])


def test_complete_shot_validation_requires_preview_before_final(monkeypatch):
    fake_bpy = _fake_shot_bpy()
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    monkeypatch.setattr(
        validation_ops,
        "validate_render_profile",
        lambda **kwargs: {
            "success": True,
            "context": {"valid": True, "resolved_device_backend": "OPTIX"},
        },
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_photographic_post",
        lambda **kwargs: {"success": True, "context": {"valid": True}},
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_motivated_lighting",
        lambda **kwargs: {"success": True, "context": {"valid": True}},
    )

    result = validate_photographic_shot(
        hero_object="Hero",
        focus_object="Eyes",
        background_object="Background",
        floor_object="Floor",
        wall_object="Wall",
        source_name="Key",
    )

    assert any(issue["code"] == "PHOTO_PREVIEW_STILL_MISSING" for issue in result["context"]["issues"])


def _mock_complete_validation_dependencies(monkeypatch, lighting_context=None):
    monkeypatch.setattr(
        validation_ops,
        "validate_render_profile",
        lambda **kwargs: {
            "success": True,
            "context": {"valid": True, "resolved_device_backend": "OPTIX"},
        },
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_photographic_post",
        lambda **kwargs: {"success": True, "context": {"valid": True}},
    )
    monkeypatch.setattr(
        validation_ops,
        "validate_motivated_lighting",
        lambda **kwargs: {
            "success": True,
            "context": lighting_context or {"valid": True, "issues": []},
        },
    )


def test_complete_shot_validation_accepts_rendered_preview_evidence(monkeypatch, tmp_path):
    fake_bpy = _fake_shot_bpy()
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    _mock_complete_validation_dependencies(monkeypatch)

    preview = tmp_path / "preview.jpg"
    preview.write_bytes(b"jpeg")
    metadata_path = Path(f"{preview.resolve()}.photographic.json")
    metadata_path.write_text(
        json.dumps(
            {
                "contract": "dcc-mcp-blender.photographic-preview.v1",
                "still_path": str(preview.resolve()),
                "profile_name": "PREVIEW",
                "resolution_percentage": 25,
                "samples": 32,
                "file_format": "JPEG",
                "device_backend": "OPTIX",
            }
        ),
        encoding="utf-8",
    )

    result = validation_ops.validate_photographic_shot(
        hero_object="Hero",
        focus_object="Eyes",
        background_object="Background",
        floor_object="Floor",
        wall_object="Wall",
        source_name="Key",
        preview_still_path=str(preview),
        require_pbr_textures=False,
    )

    codes = {issue["code"] for issue in result["context"]["issues"]}
    assert "PHOTO_PREVIEW_METADATA_MISSING" not in codes
    assert "PHOTO_PREVIEW_METADATA_MISMATCH" not in codes
    assert "PHOTO_PREVIEW_GPU_BACKEND" not in codes


def test_complete_shot_validation_promotes_background_contrast_warning(monkeypatch):
    fake_bpy = _fake_shot_bpy()
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    _mock_complete_validation_dependencies(
        monkeypatch,
        {
            "valid": True,
            "hero_background": {"background_darker_or_cooler": False},
            "issues": [{"code": "HERO_BACKGROUND_CONTRAST_MISSING", "severity": "warning"}],
        },
    )

    result = validation_ops.validate_photographic_shot(
        hero_object="Hero",
        focus_object="Eyes",
        background_object="Background",
        floor_object="Floor",
        wall_object="Wall",
        source_name="Key",
        require_preview_still=False,
        require_pbr_textures=False,
    )

    assert any(issue["code"] == "PHOTO_HERO_BACKGROUND_CONTRAST" for issue in result["context"]["issues"])


def test_photographic_shot_request_validates_before_blender_import():
    result = validate_photographic_shot(shot_type="unsupported")

    assert result["success"] is False
    assert "shot_type" in result["error"]

    result = validate_photographic_shot(scene_kind="unsupported")

    assert result["success"] is False
    assert "scene_kind" in result["error"]
