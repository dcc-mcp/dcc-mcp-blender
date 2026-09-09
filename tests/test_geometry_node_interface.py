"""Public interface discovery and editing contracts using host boundary fixtures."""

from types import SimpleNamespace

import pytest

from tests.conftest import load_and_call

PREFIX = "blender-geometry-nodes/scripts/"


class Interface:
    def __init__(self, socket):
        self.items_tree = [socket]

    def new_socket(self, name, *, in_out, socket_type):
        socket = SimpleNamespace(
            item_type="SOCKET",
            identifier="Socket_1",
            name=name,
            in_out=in_out,
            socket_type=socket_type,
            description="",
            default_value=0.0,
        )
        self.items_tree.append(socket)
        return socket

    def remove(self, socket):
        self.items_tree.remove(socket)


def interface_host():
    socket = SimpleNamespace(
        item_type="SOCKET",
        identifier="Socket_0",
        name="Scale",
        in_out="INPUT",
        socket_type="NodeSocketFloat",
        description="",
        default_value=1.0,
    )
    group = SimpleNamespace(
        name="Scatter",
        bl_idname="GeometryNodeTree",
        users=2,
        library=None,
        override_library=None,
        interface=Interface(socket),
    )
    return SimpleNamespace(data=SimpleNamespace(node_groups={group.name: group})), group


def test_interface_inspection_returns_typed_socket_identity_defaults_and_revision():
    host, group = interface_host()
    result = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)
    assert result["success"], result
    context = result["context"]
    assert context["group_users"] == 2
    assert context["revision"].startswith("gn-interface-v1:")
    assert context["sockets"][0]["identifier"] == "Socket_0"
    assert context["sockets"][0]["default_value"] == 1.0
    assert context["sockets"][0]["socket_type"] == "NodeSocketFloat"


def test_create_socket_returns_native_identifier_and_new_revision():
    host, group = interface_host()
    before = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"]
    created = load_and_call(
        PREFIX + "create_geometry_node_socket.py",
        host,
        group_name=group.name,
        name="Density",
        socket_type="NodeSocketFloat",
        in_out="INPUT",
        expected_revision=before["revision"],
    )
    assert created["success"], created
    assert created["context"]["socket"]["identifier"] == "Socket_1"
    assert created["context"]["socket"]["name"] == "Density"
    assert created["context"]["revision"] != before["revision"]


def test_update_socket_preserves_identifier_and_verifies_name_and_default():
    host, group = interface_host()
    revision = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"][
        "revision"
    ]
    result = load_and_call(
        PREFIX + "update_geometry_node_socket.py",
        host,
        group_name=group.name,
        socket_identifier="Socket_0",
        expected_revision=revision,
        new_name="Factor",
        default_value=2.5,
    )
    assert result["success"], result
    assert result["context"]["socket"]["identifier"] == "Socket_0"
    assert result["context"]["socket"]["name"] == "Factor"
    assert result["context"]["socket"]["default_value"] == 2.5
    assert result["context"]["revision"] != revision


def test_remove_socket_returns_removed_identity_and_empty_interface():
    host, group = interface_host()
    revision = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"][
        "revision"
    ]
    result = load_and_call(
        PREFIX + "remove_geometry_node_socket.py",
        host,
        group_name=group.name,
        socket_identifier="Socket_0",
        expected_revision=revision,
    )
    assert result["success"], result
    assert result["context"]["removed_socket"]["identifier"] == "Socket_0"
    assert result["context"]["sockets"] == []
    assert result["context"]["revision"] != revision


EDIT_ARGUMENTS = [
    ("create_geometry_node_socket", {"name": "Density", "in_out": "INPUT", "socket_type": "NodeSocketFloat"}),
    ("update_geometry_node_socket", {"socket_identifier": "Socket_0", "new_name": "Factor"}),
    ("remove_geometry_node_socket", {"socket_identifier": "Socket_0"}),
]


@pytest.mark.parametrize(("tool", "arguments"), EDIT_ARGUMENTS)
@pytest.mark.parametrize(
    ("condition", "code"),
    [
        ("stale", "stale_interface_revision"),
        ("malformed", "invalid_interface_revision"),
        ("linked", "local_group_required"),
        ("oversize", "interface_scan_limit"),
        ("legacy", "interface_api_unavailable"),
    ],
)
def test_edit_preconditions_fail_without_mutating_interface(tool, arguments, condition, code):
    host, group = interface_host()
    interface = group.interface
    socket = interface.items_tree[0]
    revision = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"][
        "revision"
    ]
    if condition == "stale":
        socket.default_value = 2.0
    elif condition == "malformed":
        revision = "wrong"
    elif condition == "linked":
        group.library = object()
    elif condition == "oversize":
        interface.items_tree = [socket] * 257
    elif condition == "legacy":
        group.interface = None
    count_before = len(interface.items_tree)
    result = load_and_call(PREFIX + tool + ".py", host, group_name=group.name, expected_revision=revision, **arguments)
    assert not result["success"], result
    assert result["context"]["error_code"] == code
    assert result["context"]["mutation_applied"] is False
    assert len(interface.items_tree) == count_before
    assert socket.name == "Scale"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "bad", [1, 2, 3], 1_000_001])
def test_invalid_defaults_do_not_partially_rename_socket(value):
    host, group = interface_host()
    revision = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"][
        "revision"
    ]
    result = load_and_call(
        PREFIX + "update_geometry_node_socket.py",
        host,
        group_name=group.name,
        socket_identifier="Socket_0",
        expected_revision=revision,
        new_name="Factor",
        default_value=value,
    )
    assert not result["success"], result
    assert result["context"]["error_code"] == "invalid_socket_default"
    assert result["context"]["mutation_applied"] is False
    assert group.interface.items_tree[0].name == "Scale"
    assert group.interface.items_tree[0].default_value == 1.0


def test_silent_native_remove_failure_does_not_report_success_or_rollback():
    host, group = interface_host()
    revision = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)["context"][
        "revision"
    ]
    group.interface.remove = lambda socket: None
    result = load_and_call(
        PREFIX + "remove_geometry_node_socket.py",
        host,
        group_name=group.name,
        socket_identifier="Socket_0",
        expected_revision=revision,
    )
    assert not result["success"], result
    assert result["context"]["error_code"] == "interface_edit_failed"
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False


@pytest.mark.parametrize("field", ["name", "description", "default_value"])
def test_oversized_existing_text_never_returns_unbounded_payload_or_partial_revision(field):
    host, group = interface_host()
    socket = group.interface.items_tree[0]
    socket.socket_type = "NodeSocketString"
    socket.default_value = "small"
    setattr(socket, field, "x" * 1025)
    result = load_and_call(PREFIX + "inspect_geometry_node_interface.py", host, group_name=group.name)
    assert not result["success"], result
    assert "revision" not in result["context"]
    assert "sockets" not in result["context"]
