"""E2E tests for editable shader and geometry node graphs."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _add_float_group_input(group, name: str) -> str:
    interface = getattr(group, "interface", None)
    if interface is not None and hasattr(interface, "new_socket"):
        socket = interface.new_socket(name=name, in_out="INPUT", socket_type="NodeSocketFloat")
        return socket.identifier

    socket = group.inputs.new("NodeSocketFloat", name)
    return socket.identifier


class TestNodeGraphE2E:
    def setup_method(self):
        _new_scene()

    def test_shader_node_graph_edit_chain(self):
        create_material = load_skill("blender-shader-nodes", "create_material_with_nodes")
        created = create_material.main(material_name="E2E Node Material")
        assert created["success"] is True

        ref = {"kind": "shader", "material_name": "E2E Node Material"}

        set_inputs = load_skill("blender-shader-nodes", "set_principled_inputs")
        updated = set_inputs.main(
            material_name="E2E Node Material",
            inputs={"Metallic": 0.35, "Roughness": 0.62},
        )
        assert updated["success"] is True

        create_node = load_skill("blender-shader-nodes", "create_node")
        node = create_node.main(
            node_tree_ref=ref,
            node_type="ShaderNodeValue",
            name="E2E Metallic Driver",
            location=[-450.0, 160.0],
        )
        assert node["success"] is True

        connect = load_skill("blender-shader-nodes", "connect_nodes")
        linked = connect.main(
            node_tree_ref=ref,
            from_node="E2E Metallic Driver",
            from_socket="Value",
            to_node="Principled BSDF",
            to_socket="Metallic",
        )
        assert linked["success"] is True

        list_links = load_skill("blender-shader-nodes", "list_node_links")
        links = list_links.main(node_tree_ref=ref)
        assert links["success"] is True
        assert any(link["to_socket"] == "Metallic" for link in links["context"]["links"])

        get_value = load_skill("blender-shader-nodes", "get_node_value")
        value = get_value.main(node_tree_ref=ref, node_name="Principled BSDF", socket="Roughness")
        assert value["success"] is True
        assert value["context"]["value"] == pytest.approx(0.62)

        disconnect = load_skill("blender-shader-nodes", "disconnect_nodes")
        removed = disconnect.main(
            node_tree_ref=ref,
            from_node="E2E Metallic Driver",
            to_node="Principled BSDF",
            to_socket="Metallic",
        )
        assert removed["success"] is True

        delete = load_skill("blender-shader-nodes", "delete_node")
        deleted = delete.main(node_tree_ref=ref, node_name="E2E Metallic Driver")
        assert deleted["success"] is True
        material = bpy.data.materials["E2E Node Material"]
        assert material.node_tree.nodes.get("E2E Metallic Driver") is None

    def test_geometry_node_group_modifier_chain(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        create_group = load_skill("blender-geometry-nodes", "create_geometry_node_group")
        created = create_group.main(name="E2E Geometry Graph", template="pass_through")
        assert created["success"] is True

        group = bpy.data.node_groups["E2E Geometry Graph"]
        scale_identifier = None
        if bpy.app.version >= (4, 0, 0):
            scale_identifier = _add_float_group_input(group, "Scale")

        assign_group = load_skill("blender-geometry-nodes", "assign_geometry_node_group")
        assigned = assign_group.main(
            object_name=cube_name,
            group_name="E2E Geometry Graph",
            modifier_name="E2E Geometry Nodes",
        )
        assert assigned["success"] is True

        evaluate = load_skill("blender-geometry-nodes", "evaluate_geometry_nodes_info")
        if scale_identifier is None:
            info = evaluate.main(object_name=cube_name, modifier_name="E2E Geometry Nodes")
            assert info["success"] is True
            assert info["context"]["node_count"] >= 2
            pytest.skip("Blender 3.6 uses legacy Geometry Nodes sockets; full graph edit coverage runs on 4.x")

        ref = {"kind": "geometry", "group_name": "E2E Geometry Graph"}
        connect = load_skill("blender-shader-nodes", "connect_nodes")
        linked = connect.main(
            node_tree_ref=ref,
            from_node="Group Input",
            from_socket="Geometry",
            to_node="Group Output",
            to_socket="Geometry",
        )
        assert linked["success"] is True

        set_input = load_skill("blender-geometry-nodes", "set_geometry_node_modifier_input")
        updated = set_input.main(
            object_name=cube_name,
            modifier_name="E2E Geometry Nodes",
            input_name="Scale",
            value=1.75,
        )
        assert updated["success"] is True
        assert updated["context"]["identifier"] == scale_identifier

        info = evaluate.main(object_name=cube_name, modifier_name="E2E Geometry Nodes")
        assert info["success"] is True
        assert info["context"]["node_count"] >= 2
        assert info["context"]["link_count"] >= 1
        scale_input = next(item for item in info["context"]["inputs"] if item["name"] == "Scale")
        assert scale_input["value"] == pytest.approx(1.75)
