"""Tests for the complete photographic shot validation helpers."""

from __future__ import annotations

from types import SimpleNamespace

from dcc_mcp_blender._photographic_validation_ops import _validate_surface, _validate_toy_bevel


def _surface(name: str, dimensions: tuple[float, float, float]):
    return SimpleNamespace(
        name=name,
        type="MESH",
        dimensions=dimensions,
        material_slots=[
            SimpleNamespace(
                material=SimpleNamespace(
                    use_nodes=True,
                    node_tree=SimpleNamespace(nodes=[SimpleNamespace(bl_idname="ShaderNodeTexImage")]),
                )
            )
        ],
    )


def test_surface_validation_requires_life_size_dimensions_and_textures():
    issues = []
    state = _validate_surface(_surface("Floor", (0.8, 0.8, 0.01)), "floor", issues, 1.0)

    assert state["dimensions_m"] == [0.8, 0.8, 0.01]
    assert any(issue["code"] == "PHOTO_ENVIRONMENT_SCALE" for issue in issues)


def test_toy_validation_requires_render_visible_three_segment_bevel():
    good_modifier = SimpleNamespace(
        type="BEVEL",
        name="DCC Photographic Bevel",
        width=0.0005,
        segments=3,
        limit_method="NONE",
        affect="EDGES",
        show_render=True,
    )
    bad_modifier = SimpleNamespace(
        type="BEVEL",
        name="Other Bevel",
        width=0.001,
        segments=1,
        limit_method="ANGLE",
        affect="EDGES",
        show_render=False,
    )

    good_issues = []
    good_state = _validate_toy_bevel(
        SimpleNamespace(name="Hero", type="MESH", modifiers=[good_modifier]), "Hero", good_issues
    )
    bad_issues = []
    bad_state = _validate_toy_bevel(
        SimpleNamespace(name="Part", type="MESH", modifiers=[bad_modifier]), "Part", bad_issues
    )

    assert good_state["contract_satisfied"] is True
    assert good_issues == []
    assert bad_state["contract_satisfied"] is False
    assert bad_issues[0]["code"] == "PHOTO_TOY_BEVEL"
