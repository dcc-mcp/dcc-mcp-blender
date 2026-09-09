"""Native interface CRUD, group-node port propagation and unavailable-version evidence."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


@pytest.mark.parametrize(
    ("socket_type", "default_value"),
    [
        ("NodeSocketFloat", 2.5),
        ("NodeSocketInt", 7),
        ("NodeSocketBool", True),
        ("NodeSocketVector", [0.1, 0.2, 0.3]),
        ("NodeSocketColor", [0.1, 0.2, 0.3, 1.0]),
        ("NodeSocketString", "sample"),
        ("NodeSocketGeometry", None),
    ],
)
@pytest.mark.parametrize("in_out", ["INPUT", "OUTPUT"])
def test_native_geometry_interface_crud_and_group_ports(socket_type, default_value, in_out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    group = bpy.data.node_groups.new("InterfaceFixture", "GeometryNodeTree")
    input_node = group.nodes.new("NodeGroupInput")
    output_node = group.nodes.new("NodeGroupOutput")
    inspect = load_skill("blender-geometry-nodes", "inspect_geometry_node_interface").main
    create = load_skill("blender-geometry-nodes", "create_geometry_node_socket").main
    update = load_skill("blender-geometry-nodes", "update_geometry_node_socket").main
    remove = load_skill("blender-geometry-nodes", "remove_geometry_node_socket").main
    before = inspect(group_name=group.name)
    if bpy.app.version < (4, 0, 0):
        assert not before["success"], before
        assert before["context"]["error_code"] == "interface_api_unavailable"
        assert before["context"]["mutation_applied"] is False
        return
    assert before["success"], before
    created = create(
        group_name=group.name,
        name="Parameter",
        socket_type=socket_type,
        in_out=in_out,
        expected_revision=before["context"]["revision"],
    )
    assert created["success"], created
    identifier = created["context"]["socket"]["identifier"]
    ports = input_node.outputs if in_out == "INPUT" else output_node.inputs
    assert any(port.identifier == identifier for port in ports)
    edited = update(
        group_name=group.name,
        socket_identifier=identifier,
        new_name="Renamed",
        description="Typed interface fixture",
        default_value=default_value,
        expected_revision=created["context"]["revision"],
    )
    assert edited["success"], edited
    assert edited["context"]["socket"]["identifier"] == identifier
    assert any(port.identifier == identifier and port.name == "Renamed" for port in ports)
    stale = remove(
        group_name=group.name, socket_identifier=identifier, expected_revision=created["context"]["revision"]
    )
    assert not stale["success"], stale
    assert stale["context"]["error_code"] == "stale_interface_revision"
    removed = remove(
        group_name=group.name, socket_identifier=identifier, expected_revision=edited["context"]["revision"]
    )
    assert removed["success"], removed
    assert removed["context"]["sockets"] == []
    assert not any(port.identifier == identifier for port in ports)
