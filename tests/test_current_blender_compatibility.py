"""Regressions for native API changes reproduced on Blender 5.2.1."""

from types import SimpleNamespace

from tests.conftest import load_and_call, make_mock_bpy
from tests.test_skills_geometry_nodes import FakeModifier, FakeNodeGroup, _make_mesh_obj
from tests.test_skills_rigging_pose_animation_ops import FakeFcurve


def test_geometry_modifier_reads_and_writes_rna_inputs():
    bpy = make_mock_bpy()
    obj = _make_mesh_obj()
    group = FakeNodeGroup()
    group.interface.items_tree.new_socket("Scale", "INPUT", "NodeSocketFloat")
    modifier = FakeModifier(node_group=group)
    socket = SimpleNamespace(value=1.0)
    modifier.properties = SimpleNamespace(inputs=SimpleNamespace(Scale=socket))
    obj.modifiers.append(modifier)
    bpy.data.objects.get.return_value = obj

    result = load_and_call(
        "blender-geometry-nodes/scripts/set_geometry_node_modifier_input.py",
        bpy,
        object_name="Cube",
        modifier_name=modifier.name,
        input_name="Scale",
        value=1.75,
    )

    assert result["success"], result
    assert socket.value == 1.75
    assert result["context"]["value"] == 1.75
    assert "Scale" not in modifier


def test_layered_action_queries_and_deletes_only_assigned_slot():
    bpy = make_mock_bpy()
    owned = FakeFcurve("location", 0, [1, 3])
    other = FakeFcurve("location", 0, [7, 9])
    owned_curves, other_curves = [owned], [other]
    bags = [SimpleNamespace(slot_handle=1, fcurves=other_curves), SimpleNamespace(slot_handle=2, fcurves=owned_curves)]
    action = SimpleNamespace(
        name="Shared", is_action_layered=True, layers=[SimpleNamespace(strips=[SimpleNamespace(channelbags=bags)])]
    )
    obj = SimpleNamespace(
        name="Cube", animation_data=SimpleNamespace(action=action, action_slot=SimpleNamespace(handle=2))
    )
    bpy.data.objects.get.return_value = obj

    result = load_and_call("blender-animation/scripts/get_keyframes.py", bpy, object_name="Cube")
    assert result["context"]["keyframe_count"] == 2
    assert result["context"]["fcurves"][0]["frames"] == [1.0, 3.0]

    deleted = load_and_call("blender-animation/scripts/delete_keyframes.py", bpy, object_name="Cube")
    assert deleted["success"], deleted
    assert deleted["context"]["deleted_count"] == 2
    assert owned_curves == []
    assert other_curves == [other]
    assert len(other.keyframe_points) == 2
