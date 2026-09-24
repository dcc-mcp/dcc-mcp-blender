"""Unit tests for blender-lighting skill scripts (bpy mocked)."""

from __future__ import annotations

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

    def __init__(self, default_value):
        self.default_value = default_value


class _FakeNode:
    """Minimal stand-in for a Blender shader node."""

    def __init__(self, node_type, sockets):
        self.type = node_type
        self.inputs = sockets
        self.outputs = [_FakeSocket(None)]


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

    def new(self, node_type):
        if node_type == "ShaderNodeBackground":
            node = _FakeNode(
                "BACKGROUND",
                {"Color": _FakeSocket([0.0, 0.0, 0.0, 1.0]), "Strength": _FakeSocket(1.0)},
            )
        else:
            node = _FakeNode("OUTPUT_WORLD", {"Surface": _FakeSocket(None)})
        self._nodes.append(node)
        return node


class _FakeLinks:
    def __init__(self):
        self.created = []

    def new(self, from_socket, to_socket):
        self.created.append((from_socket, to_socket))
        return MagicMock()


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
            self._node_tree.nodes.new("ShaderNodeOutputWorld")
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
        new_world = MagicMock()
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
        assert new_world.strength == 2.5

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
        bpy = _make_world_bpy(world)

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.2, 0.3, 0.4, 0.5],
        )

        assert result["success"] is True
        assert world.background_color() == [0.2, 0.3, 0.4, 0.5]

    def test_color_reaches_node_even_without_strength(self):
        """Nodes are enabled for a color-only call, so the render is affected."""
        world = _FakeWorld()
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

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.1, 0.4, 0.9])

        assert result["success"] is True
        assert world.background_color()[:3] == [0.1, 0.4, 0.9]
        assert any(node.type == "OUTPUT_WORLD" for node in world.node_tree.nodes)
        assert len(world.node_tree.links.created) == 1

    def test_reports_failure_when_color_does_not_stick(self):
        """A socket that refuses the write must surface as success=false."""
        world = _FakeWorld()
        world.use_nodes = True  # materialise the default node tree first
        bpy = _make_world_bpy(world)

        # Simulate a linked/driven socket: the assignment is accepted but the
        # stored value never changes, which is what real Blender does when the
        # socket is driven by a link or a driver.
        background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
        sticky = [0.0, 0.0, 0.0, 1.0]

        class _LockedSocket:
            @property
            def default_value(self):
                return list(sticky)

            @default_value.setter
            def default_value(self, value):
                pass  # silently ignored

        background.inputs["Color"] = _LockedSocket()

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "not applied" in result["message"]
        assert result["context"]["color"] == [0.5, 0.1, 0.1, 1.0]
