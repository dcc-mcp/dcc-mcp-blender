"""Unit tests for blender-lighting skill scripts (bpy mocked)."""

from __future__ import annotations

import os
import struct
from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_light_obj(name="Light", light_type="POINT"):
    obj = MagicMock()
    obj.name = name
    obj.type = "LIGHT"
    obj.location = [0.0, 0.0, 3.0]
    obj.data = MagicMock()
    obj.data.type = light_type
    obj.data.energy = 1000.0
    obj.data.color = [1.0, 1.0, 1.0]
    return obj


class TestCreateLight:
    def test_create_point_light(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        light_data.name = "Point Light"
        bpy.data.lights.new = MagicMock(return_value=light_data)

        obj = _make_light_obj("PointLight")
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="POINT")
        assert result["success"] is True
        bpy.data.lights.new.assert_called_once()

    def test_create_sun_light(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        bpy.data.lights.new = MagicMock(return_value=light_data)
        obj = _make_light_obj("Sun", "SUN")
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="SUN")
        assert result["success"] is True
        args, kwargs = bpy.data.lights.new.call_args
        assert kwargs.get("type") == "SUN" or "SUN" in args

    def test_invalid_type_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="INVALID")
        assert result["success"] is False

    def test_sets_energy(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        bpy.data.lights.new = MagicMock(return_value=light_data)
        obj = _make_light_obj()
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        load_and_call("blender-lighting/scripts/create_light.py", bpy, energy=5000.0)
        assert light_data.energy == 5000.0


class TestSetLightProperties:
    def test_sets_energy(self):
        bpy = make_mock_bpy()
        obj = _make_light_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-lighting/scripts/set_light_properties.py",
            bpy,
            name="Light",
            energy=2000.0,
        )
        assert result["success"] is True
        assert obj.data.energy == 2000.0

    def test_object_not_found(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-lighting/scripts/set_light_properties.py", bpy, name="Ghost")
        assert result["success"] is False

    def test_non_light_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.type = "MESH"
        bpy.data.objects.get.return_value = obj
        result = load_and_call("blender-lighting/scripts/set_light_properties.py", bpy, name="Cube")
        assert result["success"] is False


class TestListLights:
    def test_returns_only_lights(self):
        bpy = make_mock_bpy()
        light_obj = _make_light_obj("Sun", "SUN")
        mesh_obj = MagicMock()
        mesh_obj.type = "MESH"
        bpy.data.objects = [light_obj, mesh_obj]

        result = load_and_call("blender-lighting/scripts/list_lights.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["lights"][0]["name"] == "Sun"

    def test_empty_scene(self):
        bpy = make_mock_bpy(data_attrs={"objects": []})
        result = load_and_call("blender-lighting/scripts/list_lights.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 0


class _FakeSocket:
    """Minimal stand-in for a Blender node socket."""

    def __init__(self, default_value, is_linked=False, node=None):
        self.default_value = default_value
        self.is_linked = is_linked
        # Blender exposes socket.links and link.from_node / link.to_node; the
        # doubles below keep that chain so a node can be traced from a socket.
        self.links = []
        self.node = node


class _LockedSocket:
    """Socket double whose ``default_value`` silently ignores every write.

    Mirrors a socket that is driven by a link or a driver: the assignment is
    accepted, but the stored value never changes.
    """

    def __init__(self, value):
        self._value = value

    @property
    def default_value(self):
        return self._value

    @default_value.setter
    def default_value(self, value):
        pass  # silently ignored


class _Float32Socket:
    """Socket double that stores values with Blender's float32 precision."""

    def __init__(self, value=0.0):
        self._value = value

    @property
    def default_value(self):
        return struct.unpack("f", struct.pack("f", self._value))[0]

    @default_value.setter
    def default_value(self, value):
        self._value = value


class _FakeNode:
    """Minimal stand-in for a Blender shader node."""

    def __init__(self, node_type, sockets, name=None):
        self.type = node_type
        self.name = name if name is not None else node_type
        self.inputs = sockets
        self.outputs = [_FakeSocket(None)]
        for socket in list(self.inputs.values()) + self.outputs:
            socket.node = self


# Blender names duplicate nodes "Background", "Background.001", ...
_NODE_NAMES = {
    "ShaderNodeBackground": "Background",
    "ShaderNodeOutputWorld": "World Output",
}


class _FakeNodes:
    """Container that mimics ``node_tree.nodes`` including ``.new()``."""

    def __init__(self):
        self._nodes = []

    def __iter__(self):
        return iter(list(self._nodes))

    def __len__(self):
        return len(self._nodes)

    def __contains__(self, item):
        return any(node is item for node in self._nodes)

    def _unique_name(self, node_type):
        base = _NODE_NAMES.get(node_type, node_type)
        name = base
        suffix = 0
        while any(node.name == name for node in self._nodes):
            suffix += 1
            name = "{0}.{1:03d}".format(base, suffix)
        return name

    def new(self, node_type):
        name = self._unique_name(node_type)
        if node_type == "ShaderNodeBackground":
            node = _FakeNode(
                "BACKGROUND",
                {"Color": _FakeSocket([0.0, 0.0, 0.0, 1.0]), "Strength": _FakeSocket(1.0)},
                name=name,
            )
        else:
            node = _FakeNode("OUTPUT_WORLD", {"Surface": _FakeSocket(None)}, name=name)
        self._nodes.append(node)
        return node


class _FakeLink:
    """NodeLink double: Blender resolves a link to the nodes at both ends."""

    def __init__(self, from_socket, to_socket):
        self.from_socket = from_socket
        self.from_node = from_socket.node
        self.to_socket = to_socket
        self.to_node = to_socket.node


class _FakeLinks:
    def __init__(self):
        self.created = []

    def new(self, from_socket, to_socket):
        # Blender marks both ends of a link as linked and exposes it on both.
        from_socket.is_linked = True
        to_socket.is_linked = True
        link = _FakeLink(from_socket, to_socket)
        from_socket.links.append(link)
        to_socket.links.append(link)
        self.created.append((from_socket, to_socket))
        return link


def _unlink(socket):
    """Drop every link on a socket, as removing a link in Blender would."""
    socket.links.clear()
    socket.is_linked = False


class _FakeWorld:
    """World double that reproduces the real Blender background semantics.

    Blender only seeds ``ShaderNodeBackground.Color`` from ``world.color`` at
    the moment the node tree is created (when ``use_nodes`` flips False->True).
    Once the tree exists, assigning ``world.color`` leaves the socket alone --
    that divergence is the root cause of PIP-3545.
    """

    def __init__(self):
        self.color = [0.0, 0.0, 0.0]
        self._use_nodes = False
        self._node_tree = None

    @property
    def use_nodes(self):
        return self._use_nodes

    @use_nodes.setter
    def use_nodes(self, value):
        value = bool(value)
        if value and self._node_tree is None:
            # Blender materialises the default tree, seeding it from world.color.
            self._node_tree = MagicMock()
            self._node_tree.nodes = _FakeNodes()
            self._node_tree.links = _FakeLinks()
            background = self._node_tree.nodes.new("ShaderNodeBackground")
            background.inputs["Color"].default_value = list(self.color) + [1.0]
            output = self._node_tree.nodes.new("ShaderNodeOutputWorld")
            self._node_tree.links.new(background.outputs[0], output.inputs["Surface"])
        self._use_nodes = value

    @property
    def node_tree(self):
        return self._node_tree

    def background_color(self):
        """Return the live ShaderNodeBackground.Color socket value, or None."""
        if self._node_tree is None:
            return None
        for node in self._node_tree.nodes:
            if node.type == "BACKGROUND":
                return list(node.inputs["Color"].default_value)
        return None

    def background_strength(self):
        """Return the live ShaderNodeBackground.Strength socket value, or None."""
        if self._node_tree is None:
            return None
        for node in self._node_tree.nodes:
            if node.type == "BACKGROUND":
                return node.inputs["Strength"].default_value
        return None


def _make_world_bpy(world=None):
    """Build a mock bpy whose scene carries a faithful fake world."""
    bpy = make_mock_bpy()
    bpy.context.scene.world = world if world is not None else _FakeWorld()
    return bpy


def _two_background_world(orphan_feeds_spare_output=False):
    """World double whose first Background node does not drive the output.

    Returns ``(world, first, driving, surface)``. The default tree wires
    Background -> Output; that first background keeps its own link (or is left
    isolated) while a second background is wired into ``OUTPUT_WORLD.Surface``,
    so only the second one is what the renderer reads.
    """
    world = _FakeWorld()
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    first = next(node for node in nodes if node.type == "BACKGROUND")
    output = next(node for node in nodes if node.type == "OUTPUT_WORLD")
    surface = output.inputs["Surface"]
    _unlink(first.outputs[0])
    _unlink(surface)

    if orphan_feeds_spare_output:
        # Still "linked", just not to the output the renderer reads.
        spare_output = nodes.new("ShaderNodeOutputWorld")
        links.new(first.outputs[0], spare_output.inputs["Surface"])

    driving = nodes.new("ShaderNodeBackground")
    links.new(driving.outputs[0], surface)
    return world, first, driving, surface


class TestSetWorldBackground:
    def test_sets_existing_world_color(self):
        bpy = make_mock_bpy()

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.1, 0.2, 0.3],
        )

        assert result["success"] is True
        assert bpy.context.scene.world.color == [0.1, 0.2, 0.3]
        assert result["context"]["color"] == [0.1, 0.2, 0.3, 1.0]

    def test_creates_world_when_missing(self):
        bpy = make_mock_bpy()
        bpy.context.scene.world = None
        new_world = _FakeWorld()
        bpy.data.worlds.new.return_value = new_world

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.4, 0.5, 0.6, 0.7],
            strength=2.5,
        )

        assert result["success"] is True
        bpy.data.worlds.new.assert_called_once_with(name="World")
        assert bpy.context.scene.world is new_world
        assert new_world.color == [0.4, 0.5, 0.6]
        assert new_world.background_color() == [0.4, 0.5, 0.6, 0.7]
        assert new_world.background_strength() == 2.5

    def test_rejects_invalid_color_length(self):
        bpy = make_mock_bpy()

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[1.0, 0.5])

        assert result["success"] is False

    # ── Regression: PIP-3545 ─────────────────────────────────────────────────

    def test_color_is_reapplied_on_second_call(self):
        """The reported bug: only the first call used to reach the node."""
        world = _FakeWorld()
        bpy = _make_world_bpy(world)

        first = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.015, 0.02, 0.045],
            strength=1.0,
        )
        assert first["success"] is True
        assert world.background_color() == [0.015, 0.02, 0.045, 1.0]

        second = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.5, 0.1, 0.1],
            strength=2.0,
        )

        assert second["success"] is True
        assert world.background_color()[:3] == [0.5, 0.1, 0.1]
        assert world.background_strength() == 2.0

    def test_four_component_color_is_applied(self):
        world = _FakeWorld()
        world.use_nodes = True
        bpy = _make_world_bpy(world)

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.2, 0.3, 0.4, 0.5],
        )

        assert result["success"] is True
        assert world.background_color() == [0.2, 0.3, 0.4, 0.5]

    def test_color_reaches_node_even_without_strength(self):
        """With a node tree in play, a color-only call still writes the socket."""
        world = _FakeWorld()
        world.use_nodes = True  # the caller already runs this world on nodes
        bpy = _make_world_bpy(world)

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.9, 0.8, 0.7])

        assert result["success"] is True
        assert world.use_nodes is True
        assert world.background_color()[:3] == [0.9, 0.8, 0.7]

    def test_creates_background_node_when_tree_is_empty(self):
        """A world with an empty node tree gets a wired Background node."""
        world = _FakeWorld()
        world.use_nodes = True
        for node in list(world.node_tree.nodes):
            world.node_tree.nodes._nodes.remove(node)
        bpy = _make_world_bpy(world)
        links_before = len(world.node_tree.links.created)

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.1, 0.4, 0.9])

        assert result["success"] is True
        assert world.background_color()[:3] == [0.1, 0.4, 0.9]
        assert any(node.type == "OUTPUT_WORLD" for node in world.node_tree.nodes)
        assert len(world.node_tree.links.created) == links_before + 1

    def test_reports_failure_when_color_does_not_stick(self):
        """A socket that refuses the write must surface as success=false."""
        world = _FakeWorld()
        world.use_nodes = True  # materialise the default node tree first
        bpy = _make_world_bpy(world)

        # Simulate a linked/driven socket: the assignment is accepted but the
        # stored value never changes, which is what real Blender does when the
        # socket is driven by a link or a driver.
        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.inputs["Color"] = _LockedSocket([0.0, 0.0, 0.0, 1.0])

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "not applied" in result["message"]
        assert result["context"]["color"] == [0.5, 0.1, 0.1, 1.0]

    def test_reports_failure_when_color_socket_is_linked(self):
        """An HDRI-style link on Color must not be reported as success."""
        world = _FakeWorld()
        world.use_nodes = True
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.inputs["Color"].is_linked = True

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "link" in result["message"].lower()
        assert result["context"]["color"] == [0.5, 0.1, 0.1, 1.0]

    def test_reports_failure_when_background_node_is_isolated(self):
        """A background node that never reaches World Output must not be a success."""
        world = _FakeWorld()
        world.use_nodes = True
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.outputs[0].is_linked = False
        world.node_tree.links.created.clear()

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "output" in result["message"].lower()

    def test_reports_failure_when_strength_does_not_stick(self):
        world = _FakeWorld()
        world.use_nodes = True
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.inputs["Strength"] = _LockedSocket(1.0)

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1], strength=2.5
        )

        assert result["success"] is False
        assert "strength" in result["message"].lower()

    def test_color_only_call_leaves_node_free_world_alone(self):
        """Without a node tree, world.color is authoritative; nodes stay off."""
        world = _FakeWorld()
        bpy = _make_world_bpy(world)

        first = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.3, 0.6, 0.9])
        assert first["success"] is True
        assert world.use_nodes is False
        assert world.node_tree is None
        assert world.color == [0.3, 0.6, 0.9]

        # Repeated calls keep working on the non-node path.
        second = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.9, 0.8, 0.7])
        assert second["success"] is True
        assert world.color == [0.9, 0.8, 0.7]

    def test_failure_restores_use_nodes(self):
        """A rejected call must not leave the world rendering from nodes."""
        world = _FakeWorld()
        world.use_nodes = True  # build the tree
        world.use_nodes = False  # user turns nodes off; the tree is retained
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.inputs["Color"].is_linked = True

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert world.use_nodes is False, "a failed call must not switch the world onto nodes"

    def test_failure_restores_use_nodes_for_isolated_node(self):
        world = _FakeWorld()
        world.use_nodes = True
        world.use_nodes = False
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.outputs[0].is_linked = False

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert world.use_nodes is False

    def test_strength_write_back_tolerates_float32_rounding(self):
        """Large strength values read back slightly off; that is not a failure."""
        world = _FakeWorld()
        world.use_nodes = True
        bpy = _make_world_bpy(world)

        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        background.inputs["Strength"] = _Float32Socket(1.0)

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py", bpy, color=[0.1, 0.2, 0.3], strength=100.1
        )

        assert result["success"] is True
        assert abs(background.inputs["Strength"].default_value - 100.1) < 1e-3

    def test_strength_enables_nodes_on_a_node_free_world(self):
        """Asking for strength still switches the world over to nodes."""
        world = _FakeWorld()
        bpy = _make_world_bpy(world)

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py", bpy, color=[0.2, 0.2, 0.2], strength=3.0
        )

        assert result["success"] is True
        assert world.use_nodes is True
        assert world.background_color()[:3] == [0.2, 0.2, 0.2]
        assert world.background_strength() == 3.0

    # ── Regression: multiple Background nodes ────────────────────────────────

    def test_writes_the_background_node_that_drives_the_output(self):
        """The first Background is linked elsewhere; the second drives the surface."""
        world, first, driving, _ = _two_background_world(orphan_feeds_spare_output=True)
        bpy = _make_world_bpy(world)

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.2, 0.4, 0.6])

        assert result["success"] is True
        assert list(driving.inputs["Color"].default_value)[:3] == [0.2, 0.4, 0.6]
        # The node that renders nothing must be left alone, not reported as a win.
        assert list(first.inputs["Color"].default_value)[:3] == [0.0, 0.0, 0.0]

    def test_orphan_background_does_not_shadow_the_driving_one(self):
        """An isolated first Background must not fail the call nor be written."""
        world, first, driving, _ = _two_background_world()
        bpy = _make_world_bpy(world)

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.2, 0.4, 0.6])

        assert result["success"] is True
        assert list(driving.inputs["Color"].default_value)[:3] == [0.2, 0.4, 0.6]
        assert list(first.inputs["Color"].default_value)[:3] == [0.0, 0.0, 0.0]

    def test_fails_when_no_background_drives_the_output(self):
        """Two Background nodes, neither wired to the output: still a failure."""
        world, _, driving, surface = _two_background_world()
        _unlink(driving.outputs[0])
        _unlink(surface)
        world.use_nodes = False  # the caller keeps this world off nodes
        bpy = _make_world_bpy(world)

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "output" in result["message"].lower()
        assert world.use_nodes is False, "a failed call must not switch the world onto nodes"


# -- IES photometric profiles -------------------------------------------------


class _Socket:
    """Stand-in for a Blender node socket."""

    def __init__(self, name, default_value=None):
        self.name = name
        self.default_value = default_value
        self.links = []
        self.node = None

    @property
    def is_linked(self):
        return bool(self.links)


class _Link:
    def __init__(self, from_socket, to_socket):
        self.from_socket = from_socket
        self.from_node = from_socket.node
        self.to_socket = to_socket
        self.to_node = to_socket.node


class _Links:
    """NodeLink container.

    ``silent_fail`` mimics a socket that refuses the link: ``new()`` returns a
    link object but the socket never records it, which is what a write that
    looks successful but changes nothing looks like from the outside.
    """

    def __init__(self):
        self.created = []
        self.silent_fail = False

    def new(self, from_socket, to_socket):
        link = _Link(from_socket, to_socket)
        if not self.silent_fail:
            from_socket.links.append(link)
            to_socket.links.append(link)
        self.created.append(link)
        return link

    def remove(self, link):
        for socket in (link.from_socket, link.to_socket):
            if link in socket.links:
                socket.links.remove(link)
        if link in self.created:
            self.created.remove(link)


class _Node:
    """Stand-in for a Blender shader node."""

    def __init__(self, node_type, name, inputs=(), outputs=()):
        self.type = node_type
        self.name = name
        self.inputs = {}
        self.outputs = {}
        for socket in inputs:
            socket.node = self
            self.inputs[socket.name] = socket
        for socket in outputs:
            socket.node = self
            self.outputs[socket.name] = socket


class _Nodes:
    """Container mimicking ``node_tree.nodes`` including ``.new()``."""

    # Blender names duplicate nodes "IES Texture", "IES Texture.001", ...
    _NAMES = {
        "ShaderNodeTexIES": "IES Texture",
        "ShaderNodeEmission": "Emission",
        "ShaderNodeMixShader": "Mix Shader",
        "ShaderNodeValue": "Value",
        "ShaderNodeOutputLight": "Light Output",
    }

    def __init__(self):
        self._nodes = []
        self.failing_types = set()

    def __iter__(self):
        return iter(list(self._nodes))

    def __len__(self):
        return len(self._nodes)

    def __contains__(self, item):
        return any(node is item for node in self._nodes)

    def _unique_name(self, node_type):
        base = self._NAMES.get(node_type, node_type)
        name = base
        suffix = 0
        while any(node.name == name for node in self._nodes):
            suffix += 1
            name = "{0}.{1:03d}".format(base, suffix)
        return name

    def new(self, node_type):
        if node_type in self.failing_types:
            raise RuntimeError("node type {0} is not registered".format(node_type))
        name = self._unique_name(node_type)
        if node_type == "ShaderNodeTexIES":
            node = _Node(
                "TEX_IES",
                name,
                inputs=[_Socket("Vector", (0.0, 0.0, 0.0)), _Socket("Strength", 1.0)],
                outputs=[_Socket("Fac", 0.0)],
            )
            node.mode = "INTERNAL"
            node.filepath = ""
        elif node_type == "ShaderNodeEmission":
            node = _Node(
                "EMISSION",
                name,
                inputs=[_Socket("Color", (1.0, 1.0, 1.0, 1.0)), _Socket("Strength", 1.0)],
                outputs=[_Socket("Emission", (0.0, 0.0, 0.0, 1.0))],
            )
        elif node_type == "ShaderNodeValue":
            node = _Node("VALUE", name, inputs=[], outputs=[_Socket("Value", 1.0)])
        elif node_type == "ShaderNodeMixShader":
            node = _Node(
                "MIX_SHADER",
                name,
                inputs=[_Socket("Fac", 0.5), _Socket("Shader1", None), _Socket("Shader2", None)],
                outputs=[_Socket("Shader", None)],
            )
        else:
            node = _Node("OUTPUT_LIGHT", name, inputs=[_Socket("Surface", None)], outputs=[])
        self._nodes.append(node)
        return node

    def remove(self, node):
        self._nodes.remove(node)


class _LightTree:
    def __init__(self):
        self.nodes = _Nodes()
        self.links = _Links()


class _FakeLight:
    """Light double that materialises the default node tree on ``use_nodes``."""

    def __init__(self):
        self._use_nodes = False
        self._node_tree = None

    @property
    def use_nodes(self):
        return self._use_nodes

    @use_nodes.setter
    def use_nodes(self, value):
        value = bool(value)
        if value and self._node_tree is None:
            self._node_tree = _LightTree()
            emission = self._node_tree.nodes.new("ShaderNodeEmission")
            output = self._node_tree.nodes.new("ShaderNodeOutputLight")
            self._node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        self._use_nodes = value

    @property
    def node_tree(self):
        return self._node_tree


def _make_light_bpy(light=None, version=(4, 5, 0)):
    """Build a mock bpy whose scene carries one light."""
    bpy = make_mock_bpy()
    obj = MagicMock()
    obj.name = "Spot"
    obj.type = "LIGHT"
    obj.data = light if light is not None else _FakeLight()
    bpy.data.objects.get.return_value = obj
    bpy.app.version = version
    return bpy


def _ies_node(light):
    if light.node_tree is None:
        return None
    for node in light.node_tree.nodes:
        if node.type == "TEX_IES":
            return node
    return None


def _emission_node(light):
    for node in light.node_tree.nodes:
        if node.type == "EMISSION":
            return node
    return None


class TestSetLightIes:
    """Unit tests for ``set_light_ies`` (bpy mocked)."""

    def test_attaches_an_ies_node_to_the_light(self, tmp_path):
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is True
        node = _ies_node(light)
        assert node is not None, "no IES node was created"
        assert node.mode == "EXTERNAL"
        assert os.path.abspath(str(profile)) == os.path.abspath(node.filepath)

    def test_fac_drives_the_emission_node_that_feeds_the_output(self, tmp_path):
        """A node that renders nothing must not count as a success."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is True
        emission = _emission_node(light)
        link = emission.inputs["Strength"].links[0]
        assert link.from_node.type == "TEX_IES"

    def test_repeat_call_reuses_the_existing_node(self, tmp_path):
        """Calling twice must update, not stack a second profile."""
        first_path = tmp_path / "a.ies"
        first_path.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        second_path = tmp_path / "b.ies"
        second_path.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(first_path))
        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(second_path))

        ies_nodes = [node for node in light.node_tree.nodes if node.type == "TEX_IES"]
        assert len(ies_nodes) == 1
        assert os.path.abspath(str(second_path)) == os.path.abspath(ies_nodes[0].filepath)

    def test_strength_is_applied_and_read_back(self, tmp_path):
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py",
            bpy,
            light_name="Spot",
            ies_path=str(profile),
            strength=2.5,
        )

        assert result["success"] is True
        assert _ies_node(light).inputs["Strength"].default_value == 2.5
        assert result["context"]["strength"] == 2.5

    def test_clear_removes_the_node_and_restores_strength(self, tmp_path):
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)
        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile))

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", clear=True)

        assert result["success"] is True
        assert _ies_node(light) is None
        assert _emission_node(light).inputs["Strength"].default_value == 1.0
        assert _emission_node(light).inputs["Strength"].links == []

    def test_clear_on_a_light_without_a_profile(self):
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", clear=True)

        assert result["success"] is True
        assert result["context"]["removed"] == 0

    def test_missing_profile_file_is_refused(self, tmp_path):
        """Blender accepts a missing path and then renders unshaped; refuse instead."""
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py",
            bpy,
            light_name="Spot",
            ies_path=str(tmp_path / "absent.ies"),
        )

        assert result["success"] is False
        assert _ies_node(light) is None

    def test_no_path_and_no_clear_is_refused(self):
        bpy = _make_light_bpy()

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot")

        assert result["success"] is False

    def test_unknown_light_is_refused(self, tmp_path):
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        bpy.app.version = (4, 5, 0)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Ghost", ies_path=str(profile)
        )

        assert result["success"] is False

    def test_non_light_object_is_refused(self, tmp_path):
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.type = "MESH"
        bpy.data.objects.get.return_value = obj
        bpy.app.version = (4, 5, 0)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Cube", ies_path=str(profile)
        )

        assert result["success"] is False

    def test_older_blender_is_refused_with_a_stated_reason(self, tmp_path):
        """Version handling is explicit, not a hasattr guess."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light, version=(3, 6, 5))

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert "3.6.5" in result["message"] + str(result.get("error") or "")
        assert _ies_node(light) is None

    def test_build_without_the_node_type_is_refused(self, tmp_path):
        """A build that cannot create the node refuses instead of no-opping."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        light.node_tree.nodes.failing_types.add("ShaderNodeTexIES")
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert "ShaderNodeTexIES" in result["message"] + str(result.get("error") or "")

    def test_reports_failure_when_the_link_does_not_take(self, tmp_path):
        """A wiring that never lands must surface as success=false.

        The node can be created and configured correctly while the link is
        refused, which leaves the light rendering unshaped. Only reading the
        tree back catches that, so this is the test that fails if the
        verification step is removed.
        """
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        light.node_tree.links.silent_fail = True
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert _ies_node(light) is not None, "the node was still created; the link is what failed"

    def test_vector_input_is_left_unconnected(self, tmp_path):
        """Connecting a geometry direction there mis-aims the beam."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile))

        assert _ies_node(light).inputs["Vector"].links == []

    def test_second_emission_node_does_not_shadow_the_driving_one(self, tmp_path):
        """With two emission nodes, the one feeding the output is the one wired."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        emission = _emission_node(light)
        output = next(node for node in tree.nodes if node.type == "OUTPUT_LIGHT")
        surface = output.inputs["Surface"]
        tree.links.remove(surface.links[0])
        driving = tree.nodes.new("ShaderNodeEmission")
        tree.links.new(driving.outputs["Emission"], surface)
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is True
        assert driving.inputs["Strength"].links[0].from_node.type == "TEX_IES"
        assert emission.inputs["Strength"].links == []

    def test_refuses_when_a_non_emission_node_drives_the_output(self, tmp_path):
        """A MIX shader feeding the output leaves the profile nowhere to land.

        Every check on the IES node itself still passes in this shape -- the node
        is in the tree, the path matches, its Fac is linked to a Strength input --
        so anchoring verification to the node rather than to whatever drives the
        light output reports success for a light that renders unshaped.
        """
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        mix = tree.nodes.new("ShaderNodeMixShader")
        orphan = tree.nodes.new("ShaderNodeEmission")
        output = next(node for node in tree.nodes if node.type == "OUTPUT_LIGHT")
        surface = output.inputs["Surface"]
        for link in list(surface.links):
            tree.links.remove(link)
        tree.links.new(mix.outputs["Shader"], surface)
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert "MIX_SHADER" in result["message"]
        # Refusing must not leave a half-wired profile behind.
        assert _ies_node(light) is None
        assert orphan.inputs["Strength"].links == []
        assert [link.from_node for link in surface.links] == [mix]

    def test_refuses_when_no_emission_node_exists_to_drive(self, tmp_path):
        """Same shape, but with no emission node in the tree at all.

        The temptation here is to create one and wire the profile into it; it
        would render nothing, because the output is still fed by the mix shader.
        """
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        # Drop the default emission node too, so the tree really has none.
        for node in [node for node in tree.nodes if node.type == "EMISSION"]:
            tree.nodes.remove(node)
        mix = tree.nodes.new("ShaderNodeMixShader")
        output = next(node for node in tree.nodes if node.type == "OUTPUT_LIGHT")
        surface = output.inputs["Surface"]
        for link in list(surface.links):
            tree.links.remove(link)
        tree.links.new(mix.outputs["Shader"], surface)
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert _ies_node(light) is None
        assert [node for node in tree.nodes if node.type == "EMISSION"] == []
        assert [link.from_node for link in surface.links] == [mix]

    def test_takes_over_an_unconnected_output(self, tmp_path):
        """Nothing drives the light output yet, so the light can be taken over."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        output = next(node for node in tree.nodes if node.type == "OUTPUT_LIGHT")
        surface = output.inputs["Surface"]
        for link in list(surface.links):
            tree.links.remove(link)
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is True
        assert surface.links, "the emission node was not wired into the light output"
        emission = surface.links[0].from_node
        assert emission.type == "EMISSION"
        assert emission.inputs["Strength"].links[0].from_node.type == "TEX_IES"

    # ── clear must not touch wiring it did not create ────────────────────────

    def test_clear_leaves_the_users_own_strength_wiring_alone(self):
        """A Value node driving Strength is the user's, not ours, to remove.

        With no profile on the light there is nothing to clear, so a call that
        still unwired the socket and reset its value would be silent data loss
        on a light the caller never gave an IES profile to.
        """
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        emission = _emission_node(light)
        value = tree.nodes.new("ShaderNodeValue")
        strength = emission.inputs["Strength"]
        strength.default_value = 3.0
        tree.links.new(value.outputs["Value"], strength)
        bpy = _make_light_bpy(light)

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", clear=True)

        assert result["success"] is True
        assert result["context"]["removed"] == 0
        assert [link.from_node.type for link in strength.links] == ["VALUE"]
        assert strength.default_value == 3.0, "clearing must not reset a value it never set"

    def test_clear_removes_only_the_ies_link(self, tmp_path):
        """An IES link goes; a neighbouring Value link does not."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile))

        tree = light.node_tree
        emission = _emission_node(light)
        # The IES link is removed with the node; add a second, user-owned link
        # to the same socket to prove only ours is touched.
        value = tree.nodes.new("ShaderNodeValue")
        strength = emission.inputs["Strength"]
        strength.default_value = 5.0
        tree.links.new(value.outputs["Value"], strength)

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", clear=True)

        assert result["success"] is True
        assert _ies_node(light) is None
        assert [link.from_node.type for link in strength.links] == ["VALUE"]
        assert strength.default_value == 5.0

    def test_clear_does_not_reset_strength_on_an_unrelated_emission(self, tmp_path):
        """With two emission nodes, only the IES-driven one is touched."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile))

        tree = light.node_tree
        orphan = tree.nodes.new("ShaderNodeEmission")
        value = tree.nodes.new("ShaderNodeValue")
        orphan_strength = orphan.inputs["Strength"]
        orphan_strength.default_value = 7.0
        tree.links.new(value.outputs["Value"], orphan_strength)

        result = load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", clear=True)

        assert result["success"] is True
        assert [link.from_node.type for link in orphan_strength.links] == ["VALUE"]
        assert orphan_strength.default_value == 7.0, "clearing hit an emission node it does not own"

    # ── the node that renders is the one that must be configured ─────────────

    def test_configures_the_ies_node_that_is_driving(self, tmp_path):
        """With two IES nodes, the one wired to Strength is the one to write.

        Taking the first IES node in the tree would report success with the new
        path while the renderer kept reading the other node's profile.
        """
        first = tmp_path / "old.ies"
        first.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        second = tmp_path / "new.ies"
        second.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        load_and_call("blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(first))

        tree = light.node_tree
        emission = _emission_node(light)
        original = _ies_node(light)
        # A second IES node takes over the socket, as a hand-edited tree would.
        takeover = tree.nodes.new("ShaderNodeTexIES")
        takeover.mode = "EXTERNAL"
        takeover.filepath = str(first)
        strength = emission.inputs["Strength"]
        for link in list(strength.links):
            tree.links.remove(link)
        tree.links.new(takeover.outputs["Fac"], strength)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(second)
        )

        assert result["success"] is True
        driving = strength.links[0].from_node
        assert driving is takeover, "the profile was written to a node that renders nothing"
        assert os.path.abspath(driving.filepath) == os.path.abspath(str(second))
        assert result["context"]["node_name"] == driving.name
        # The superseded node is left alone rather than silently mutated.
        assert os.path.abspath(original.filepath) == os.path.abspath(str(first))

    def test_reports_the_node_that_renders(self, tmp_path):
        """The reported node name is the one carrying the requested profile."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        emission = _emission_node(light)
        driving = emission.inputs["Strength"].links[0].from_node
        assert result["success"] is True
        assert result["context"]["node_name"] == driving.name
        assert os.path.abspath(driving.filepath) == os.path.abspath(str(profile))

    # ── taking over the socket must never leave the light worse off ──────────

    def test_restores_the_previous_link_when_the_rewire_fails(self, tmp_path):
        """A rewire that does not land must put back what was there before.

        The caller reads success=False as \"nothing changed\". If the take-over
        already removed their link, that reading is wrong and the light is left
        with nothing driving Strength.
        """
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        emission = _emission_node(light)
        value = tree.nodes.new("ShaderNodeValue")
        strength = emission.inputs["Strength"]
        tree.links.new(value.outputs["Value"], strength)
        bpy = _make_light_bpy(light)

        # Everything lands until the tool has taken the old link off, then the
        # new link refuses to register -- but a later re-link can still succeed.
        state = {"removed": False, "failed_once": False}
        real_remove = tree.links.remove
        real_new = tree.links.new

        def remove(link):
            state["removed"] = True
            return real_remove(link)

        def new(from_socket, to_socket):
            if state["removed"] and not state["failed_once"]:
                state["failed_once"] = True
                return None
            return real_new(from_socket, to_socket)

        tree.links.remove = remove
        tree.links.new = new

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert [link.from_node.type for link in strength.links] == ["VALUE"], (
            "the previous wiring was not restored after a failed take-over"
        )
        assert result["context"]["previous_link"] == "VALUE"
        assert result["context"]["took_over_link"] is True
        assert result["context"]["previous_link_restored"] is True

    def test_says_so_when_the_previous_link_cannot_be_restored(self, tmp_path):
        """An unrecoverable take-over must be reported, not assumed recovered.

        The wiring cannot be put back here, so the error has to carry that
        rather than let the caller believe the light is as it was.
        """
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        emission = _emission_node(light)
        value = tree.nodes.new("ShaderNodeValue")
        strength = emission.inputs["Strength"]
        tree.links.new(value.outputs["Value"], strength)
        bpy = _make_light_bpy(light)

        state = {"removed": False}
        real_remove = tree.links.remove

        def remove(link):
            state["removed"] = True
            return real_remove(link)

        # Nothing can be linked once the take-over has started.
        tree.links.remove = remove
        tree.links.new = lambda from_socket, to_socket: None

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is False
        assert result["context"]["previous_link_restored"] is False
        assert "could not be restored" in (result.get("error") or "")

    def test_reports_taking_over_existing_wiring(self, tmp_path):
        """A successful take-over is reported, not done quietly."""
        profile = tmp_path / "profile.ies"
        profile.write_text("IESNA:LM-63-2002\n", encoding="utf-8")
        light = _FakeLight()
        light.use_nodes = True
        tree = light.node_tree
        emission = _emission_node(light)
        value = tree.nodes.new("ShaderNodeValue")
        tree.links.new(value.outputs["Value"], emission.inputs["Strength"])
        bpy = _make_light_bpy(light)

        result = load_and_call(
            "blender-lighting/scripts/set_light_ies.py", bpy, light_name="Spot", ies_path=str(profile)
        )

        assert result["success"] is True
        # The caller's Value node was replaced, so say which one went.
        assert result["context"]["replaced_link"] == "VALUE"
        driving = emission.inputs["Strength"].links[0].from_node
        assert driving.type == "TEX_IES"
        assert os.path.abspath(driving.filepath) == os.path.abspath(str(profile))
