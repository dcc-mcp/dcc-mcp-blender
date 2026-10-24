"""Blender 5.x API-shape regressions, not a substitute for native tests."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcc_mcp_blender import _compositor_ops as comp
from dcc_mcp_blender import _node_graph_ops as graph
from tests.test_skills_compositor import (
    _NODE_SOCKETS,
    FakeNodeCollection,
    FakeNodeTree,
    FakeSceneCollection,
    FakeSocket,
    FakeSocketCollection,
)


class ModernInterface:
    def __init__(self, tree):
        self.tree = tree
        self.items_tree = []

    def new_socket(self, name, in_out, socket_type):
        socket = SimpleNamespace(
            name=name,
            in_out=in_out,
            socket_type=socket_type,
            item_type="SOCKET",
            identifier="Socket_" + str(len(self.items_tree)),
        )
        self.items_tree.append(socket)
        for node in self.tree.nodes:
            if node.bl_idname == "NodeGroupOutput":
                self.tree.sync_output(node)
        return socket

    def remove(self, socket):
        self.items_tree.remove(socket)


class ModernNodes(FakeNodeCollection):
    def new(self, type):
        if type in {"CompositorNodeComposite", "CompositorNodeMath", "CompositorNodeTexture"}:
            raise RuntimeError("Node type removed in 5.0: " + type)
        if type == "CompositorNodeNotReal":
            raise RuntimeError("Unknown node type")
        node = super().new(type)
        if type == "NodeGroupOutput":
            node.is_active_output = not any(getattr(n, "is_active_output", False) for n in self._tree.nodes)
            self._tree.sync_output(node)
        if type == "ShaderNodeMath":
            layout = _NODE_SOCKETS["CompositorNodeMath"]
            node.inputs = FakeSocketCollection([FakeSocket(*x) for x in layout["inputs"]])
            node.outputs = FakeSocketCollection([FakeSocket(*x) for x in layout["outputs"]])
        return node


class ModernTree(FakeNodeTree):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.bl_idname = "CompositorNodeTree"
        self.nodes = ModernNodes(self)
        self.interface = ModernInterface(self)
        self.library = None
        self.override_library = None
        self.users = 1

    def sync_output(self, node):
        node.inputs = FakeSocketCollection(
            [
                FakeSocket(s.name, [0.0, 0.0, 0.0, 1.0], "RGBA")
                for s in self.interface.items_tree
                if s.in_out == "OUTPUT"
            ]
        )
        for socket, interface in zip(node.inputs, (s for s in self.interface.items_tree if s.in_out == "OUTPUT")):
            socket.identifier = interface.identifier
            socket._node = node

    def copy(self):
        import copy

        return copy.deepcopy(self)


class ModernGroups:
    def __init__(self):
        self.items = []

    def new(self, name, type):
        tree = ModernTree(name)
        self.items.append(tree)
        return tree

    def remove(self, tree):
        if tree in self.items:
            self.items.remove(tree)

    def __iter__(self):
        return iter(self.items)


class ModernScene:
    def __init__(self, name="Scene"):
        self.name = name
        self.compositing_node_group = None
        self.render = SimpleNamespace(use_compositing=True)
        self.library = None
        self.override_library = None

    @property
    def use_nodes(self):
        return True

    @use_nodes.setter
    def use_nodes(self, value):
        pass  # Native 5.x deprecated setter is a no-op.


def modern_bpy():
    scene = ModernScene()
    return SimpleNamespace(
        app=SimpleNamespace(version=(5, 2, 1), version_string="5.2.1"),
        context=SimpleNamespace(scene=scene),
        data=SimpleNamespace(scenes=FakeSceneCollection([scene]), node_groups=ModernGroups(), materials=[]),
    )


def test_modern_enable_writes_actual_render_switch():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        result = comp.set_compositor_enabled(enabled=False)
    assert result["success"], result
    assert bpy.context.scene.render.use_compositing is False
    assert bpy.context.scene.compositing_node_group is None
    assert result["context"]["use_nodes"] is False  # Legacy result key remains an effective-state alias.


def test_modern_default_tree_has_native_group_output_and_is_readable():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        result = comp.setup_compositor_tree()
        assert result["success"], result
        tree = bpy.context.scene.compositing_node_group
        assert tree is not None
        outputs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
        assert len(outputs) == 1
        assert [s.socket_type for s in tree.interface.items_tree if s.in_out == "OUTPUT"][0] == "NodeSocketColor"
        assert len(tree.links) == 1
        assert graph.get_compositor_node_tree()["success"]
        assert graph.list_nodes({"kind": "compositor"})["success"]
        assert any(x["kind"] == "compositor" for x in graph.list_all_node_graphs()["context"]["node_graphs"])
        again = comp.setup_compositor_tree()
        assert again["success"], again
        assert len(bpy.context.scene.compositing_node_group.nodes) == 2
        assert len(bpy.context.scene.compositing_node_group.links) == 1


def test_modern_crud_and_math_alias():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        created = comp.create_compositor_node("math", name="Gain")
        assert created["success"], created
        assert created["context"]["node_type"] == "ShaderNodeMath"
        result = comp.set_compositor_node_value("Gain", "Value", 0.25)
        assert result["success"], result
        assert comp.get_compositor_node_value("Gain", "Value")["context"]["value"] == 0.25
        assert comp.delete_compositor_node("Gain")["success"]
        assert comp.clear_compositor_tree()["success"]
        assert len(bpy.context.scene.compositing_node_group.nodes) == 0


def test_invalid_create_does_not_publish_tree_or_enable_render():
    bpy = modern_bpy()
    bpy.context.scene.render.use_compositing = False
    with patch.dict("sys.modules", bpy=bpy):
        result = comp.create_compositor_node("CompositorNodeNotReal")
    assert not result["success"]
    assert bpy.context.scene.compositing_node_group is None
    assert bpy.context.scene.render.use_compositing is False
    assert bpy.data.node_groups.items == []


@pytest.mark.parametrize("location", [[float("nan"), 0], [0, float("inf")], ["bad", 0]])
def test_invalid_location_does_not_modify_existing_tree(location):
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        tree = bpy.context.scene.compositing_node_group
        before = list(tree.nodes)
        result = comp.create_compositor_node("blur", location=location)
    assert not result["success"]
    assert list(tree.nodes) == before


def test_named_scene_read_uses_requested_scene_not_active():
    bpy = modern_bpy()
    other = ModernScene("Other")
    bpy.data.scenes = FakeSceneCollection([bpy.context.scene, other])
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree(scene_name="Other")["success"]
        result = graph.list_nodes({"kind": "compositor", "scene_name": "Other"})
        assert result["success"], result
    assert bpy.context.scene.compositing_node_group is None


def test_shared_group_edits_reject_and_clear_only_rebinds_requested_scene():
    bpy = modern_bpy()
    other = ModernScene("Other")
    bpy.data.scenes = FakeSceneCollection([bpy.context.scene, other])
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        tree = bpy.context.scene.compositing_node_group
        other.compositing_node_group = tree
        tree.users = 2
        before = list(tree.nodes)
        ref = {"kind": "compositor"}
        calls = (
            lambda: comp.create_compositor_node("blur"),
            lambda: comp.delete_compositor_node("Render Layers"),
            lambda: comp.connect_compositor_nodes("Render Layers", "Image", "Composite", "Image"),
            lambda: comp.disconnect_compositor_nodes(from_node="Render Layers"),
            lambda: comp.set_compositor_node_value("Composite", "Image", [1, 0, 0, 1]),
            lambda: comp.setup_compositor_tree(),
            lambda: graph.create_node(ref, "CompositorNodeBlur"),
            lambda: graph.delete_node(ref, "Render Layers"),
            lambda: graph.connect_nodes(ref, "Render Layers", "Image", "Composite", "Image"),
            lambda: graph.disconnect_nodes(ref, from_node="Render Layers"),
            lambda: graph.set_node_input(ref, "Composite", "Image", [1, 0, 0, 1]),
        )
        for call in calls:
            result = call()
            assert not result["success"], result
            assert list(tree.nodes) == before
        assert graph.list_nodes(ref)["success"]
        assert comp.clear_compositor_tree()["success"]
    assert other.compositing_node_group is tree
    assert list(tree.nodes) == before
    assert bpy.context.scene.compositing_node_group is not tree
    assert len(bpy.context.scene.compositing_node_group.nodes) == 0


def test_invalid_existing_output_interface_preserves_graph_and_render_state():
    bpy = modern_bpy()
    tree = bpy.data.node_groups.new("Existing", "CompositorNodeTree")
    tree.interface.new_socket("Wrong", "OUTPUT", "NodeSocketFloat")
    bpy.context.scene.compositing_node_group = tree
    bpy.context.scene.render.use_compositing = False
    with patch.dict("sys.modules", bpy=bpy):
        result = comp.setup_compositor_tree()
    assert not result["success"]
    assert len(tree.nodes) == 0
    assert len(tree.interface.items_tree) == 1
    assert tree.interface.items_tree[0].socket_type == "NodeSocketFloat"
    assert bpy.context.scene.render.use_compositing is False


def test_disabled_modern_reads_keep_render_disabled():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        assert comp.set_compositor_enabled(enabled=False)["success"]
        tree = bpy.context.scene.compositing_node_group
        for call in (
            lambda: comp.list_compositor_node_links(),
            lambda: graph.get_compositor_node_tree(),
            lambda: graph.list_nodes({"kind": "compositor"}),
            lambda: graph.list_all_node_graphs(),
        ):
            assert call()["success"]
            assert bpy.context.scene.render.use_compositing is False
            assert bpy.context.scene.compositing_node_group is tree


def test_default_setup_uses_active_group_output_not_preferred_name():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        tree = bpy.context.scene.compositing_node_group
        inactive = tree.nodes.get("Composite")
        inactive.is_active_output = False
        active = tree.nodes.new("NodeGroupOutput")
        active.name = "Active Output"
        active.is_active_output = True
        assert list(active.inputs)[0].identifier != list(active.inputs)[0].name
        assert comp.setup_compositor_tree()["success"]
    assert any(link.to_node is active for link in tree.links)
    assert active.is_active_output and not inactive.is_active_output


def test_rejected_output_interface_keeps_existing_muted_link_identity():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        tree = bpy.context.scene.compositing_node_group
        original = next(iter(tree.links))
        original.is_muted = True
        tree.interface.items_tree[0].socket_type = "NodeSocketFloat"
        assert not comp.setup_compositor_tree()["success"]
    assert list(tree.links) == [original]
    assert original.is_muted


def test_catalog_current_ids_are_searchable_and_accepted():
    bpy = modern_bpy()
    bpy.types = SimpleNamespace(ShaderNodeValue=object, ShaderNodeGamma=object, ShaderNodeMath=object)
    with patch.dict("sys.modules", bpy=bpy):
        for current in ("ShaderNodeValue", "ShaderNodeGamma", "ShaderNodeMath"):
            entries = comp.list_compositor_node_types(search=current)["context"]["node_types"]
            assert len(entries) == 1 and entries[0]["id"] == current
            assert entries[0]["registered"]
            assert comp.create_compositor_node(entries[0]["id"])["success"]
    assert comp.resolve_compositor_node_type("ShaderNodeTexImage") is None


@pytest.mark.parametrize("operation", ["setup", "create", "clear"])
def test_linked_scene_does_not_leak_staged_group(operation):
    bpy = modern_bpy()
    scene = bpy.context.scene
    with patch.dict("sys.modules", bpy=bpy):
        if operation == "clear":
            assert comp.setup_compositor_tree()["success"]
        original = scene.compositing_node_group
        groups = list(bpy.data.node_groups)
        scene.library = object()
        call = {
            "setup": lambda: comp.setup_compositor_tree(clear=True),
            "create": lambda: comp.create_compositor_node("blur"),
            "clear": lambda: comp.clear_compositor_tree(),
        }[operation]
        assert not call()["success"]
        assert scene.compositing_node_group is original
        assert list(bpy.data.node_groups) == groups


def test_future_effect_stack_api_is_not_silently_treated_as_52():
    bpy = modern_bpy()
    bpy.app.version = (5, 3, 0)
    with patch.dict("sys.modules", bpy=bpy):
        assert not comp.setup_compositor_tree()["success"]
        assert not comp.list_compositor_node_types()["success"]
    assert bpy.data.node_groups.items == []


def test_fake_user_does_not_count_as_another_scene_owner():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        tree = bpy.context.scene.compositing_node_group
        tree.use_fake_user = True
        tree.users = 2
        assert comp.create_compositor_node("blur")["success"]
        assert graph.create_node({"kind": "compositor"}, "CompositorNodeBlur")["success"]


def test_failed_group_binding_discards_staged_group():
    class ReadOnlyBinding(ModernScene):
        @property
        def compositing_node_group(self):
            return None

        @compositing_node_group.setter
        def compositing_node_group(self, value):
            if value is not None:
                raise RuntimeError("Read-only binding")

    bpy = modern_bpy()
    bpy.context.scene = ReadOnlyBinding()
    bpy.data.scenes = FakeSceneCollection([bpy.context.scene])
    with patch.dict("sys.modules", bpy=bpy):
        for call in (lambda: comp.setup_compositor_tree(), lambda: comp.create_compositor_node("blur")):
            assert not call()["success"]
            assert bpy.data.node_groups.items == []
            assert bpy.context.scene.compositing_node_group is None


def test_failed_enable_restores_replaced_link_and_mute_state():
    from tests.test_skills_compositor import FakeLinkCollection

    class SingleInputLinks(FakeLinkCollection):
        def new(self, source, target):
            for existing in list(self):
                if existing.to_socket is target:
                    self.remove(existing)
            link = super().new(source, target)
            link.is_muted = False
            return link

    class RejectEnable:
        @property
        def use_compositing(self):
            return False

        @use_compositing.setter
        def use_compositing(self, value):
            if value:
                raise RuntimeError("Render state is locked")

    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        assert comp.setup_compositor_tree()["success"]
        assert comp.create_compositor_node("blur", name="Existing Source")["success"]
        tree = bpy.context.scene.compositing_node_group
        tree.links = SingleInputLinks()
        source = tree.nodes.get("Existing Source").outputs.get("Image")
        target = tree.nodes.get("Composite").inputs.get("Image")
        tree.links.new(source, target).is_muted = True
        bpy.context.scene.render = RejectEnable()
        assert not comp.setup_compositor_tree()["success"]
    links = list(tree.links)
    assert len(links) == 1
    assert links[0].from_socket is source and links[0].to_socket is target
    assert links[0].is_muted
    assert bpy.context.scene.render.use_compositing is False


def test_modern_missing_group_has_actionable_setup_hint():
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy):
        result = graph.list_nodes({"kind": "compositor"})
    assert not result["success"]
    assert "setup_compositor_tree" in str(result)
    assert "scene.use_nodes" not in str(result)


@pytest.mark.parametrize("unsupported", ["future_version", "missing_feature"])
def test_unsupported_compositor_keeps_other_graph_discovery(unsupported):
    bpy = modern_bpy()
    bpy.data.materials = [SimpleNamespace(name="Material", use_nodes=True, node_tree=FakeNodeTree())]
    geometry = ModernTree("Geometry")
    geometry.bl_idname = "GeometryNodeTree"
    bpy.data.node_groups.items.append(geometry)
    if unsupported == "future_version":
        bpy.app.version = (5, 3, 0)
    else:
        del bpy.context.scene.compositing_node_group
    with patch.dict("sys.modules", bpy=bpy):
        result = graph.list_all_node_graphs()
        assert result["success"], result
        context = result["context"]
        assert context["count"] == 2
        assert {item["kind"] for item in context["node_graphs"]} == {"shader", "geometry"}
        assert context["unavailable_graphs"][0]["kind"] == "compositor"
        assert context["unavailable_graphs"][0]["reason"]
        assert not comp.setup_compositor_tree()["success"]


@pytest.mark.parametrize("error", [ValueError("unexpected native tree failure"), RuntimeError("native failure")])
def test_graph_discovery_does_not_swallow_unrelated_native_errors(error):
    bpy = modern_bpy()
    with patch.dict("sys.modules", bpy=bpy), patch.object(graph, "compositor_tree", side_effect=error):
        result = graph.list_all_node_graphs()
    assert not result["success"]
