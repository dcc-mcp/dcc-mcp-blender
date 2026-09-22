"""Unit tests for the blender-compositor skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path

import yaml

from dcc_mcp_blender._compositor_ops import resolve_compositor_node_type
from tests.conftest import load_and_call, make_mock_bpy

COMPOSITOR_PATH = "src/dcc_mcp_blender/skills/blender-compositor/tools.yaml"
SKILL = "blender-compositor"


# ---------------------------------------------------------------------------
# Fake compositor graph
# ---------------------------------------------------------------------------


class FakeSocket:
    def __init__(self, name, default_value=0.0, socket_type="VALUE"):
        self.name = name
        self.identifier = name
        self.default_value = default_value
        self.type = socket_type
        self.is_linked = False


class FakeSocketCollection:
    def __init__(self, sockets):
        self._sockets = list(sockets)

    def get(self, name):
        for socket in self._sockets:
            if socket.name == name or socket.identifier == name:
                return socket
        return None

    def __iter__(self):
        return iter(self._sockets)

    def __len__(self):
        return len(self._sockets)


RGBA = [0.0, 0.0, 0.0, 1.0]


# Socket layout for the node types the tests exercise. Nodes created through
# ``nodes.new`` mirror Blender's naming so wiring assertions stay realistic.
_NODE_SOCKETS = {
    "CompositorNodeRLayers": {"inputs": [], "outputs": [("Image", RGBA), ("Alpha", 1.0)]},
    "CompositorNodeComposite": {
        "inputs": [("Image", list(RGBA)), ("Alpha", 1.0)],
        "outputs": [],
    },
    "CompositorNodeViewer": {"inputs": [("Image", list(RGBA)), ("Alpha", 1.0)], "outputs": []},
    "CompositorNodeDenoise": {
        "inputs": [("Image", list(RGBA)), ("Normal", list(RGBA)), ("Albedo", list(RGBA))],
        "outputs": [("Image", list(RGBA))],
    },
    "CompositorNodeBlur": {
        "inputs": [("Size X", 0.0), ("Size Y", 0.0), ("Image", list(RGBA))],
        "outputs": [("Image", list(RGBA))],
    },
    "CompositorNodeGlare": {
        "inputs": [("Image", list(RGBA)), ("Mix", 0.0)],
        "outputs": [("Image", list(RGBA))],
    },
    "CompositorNodeMath": {"inputs": [("Value", 0.0)], "outputs": [("Value", 0.0)]},
}


class FakeNode:
    def __init__(self, bl_idname, name=None, inputs=(), outputs=()):
        self.bl_idname = bl_idname
        self.name = name or bl_idname
        self.label = ""
        self.type = bl_idname.replace("CompositorNode", "").upper()
        self.location = (0.0, 0.0)
        if not inputs and not outputs:
            layout = _NODE_SOCKETS.get(bl_idname, {})
            inputs = layout.get("inputs", ())
            outputs = layout.get("outputs", ())
        self.inputs = FakeSocketCollection(
            FakeSocket(entry[0], entry[1] if len(entry) > 1 else 0.0) for entry in inputs
        )
        self.outputs = FakeSocketCollection(
            FakeSocket(entry[0], entry[1] if len(entry) > 1 else 0.0) for entry in outputs
        )
        for socket in list(self.inputs) + list(self.outputs):
            socket._node = self  # noqa: SLF001 - back-reference for link endpoints


class FakeNodeCollection:
    def __init__(self):
        self._nodes = []

    def get(self, name):
        for node in self._nodes:
            if node.name == name:
                return node
        return None

    def new(self, type):  # noqa: A002 - Blender passes the id as ``type``
        node = FakeNode(type)
        self._nodes.append(node)
        return node

    def remove(self, node):
        self._nodes.remove(node)

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self):
        return len(self._nodes)


class FakeLink:
    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class FakeLinkCollection:
    def __init__(self):
        self._links = []

    def new(self, from_socket, to_socket):
        link = FakeLink(
            _owner(from_socket),
            from_socket,
            _owner(to_socket),
            to_socket,
        )
        from_socket.is_linked = True
        to_socket.is_linked = True
        self._links.append(link)
        return link

    def remove(self, link):
        link.to_socket.is_linked = False
        self._links.remove(link)

    def __iter__(self):
        return iter(self._links)

    def __len__(self):
        return len(self._links)


def _owner(socket):
    """Return the node that owns *socket* (test helper, mirrors link endpoints)."""
    return socket._node  # noqa: SLF001 - set by FakeNode.__init__


class FakeNodeTree:
    def __init__(self):
        self.nodes = FakeNodeCollection()
        self.links = FakeLinkCollection()


class FakeScene:
    """Scene whose ``node_tree`` appears only once ``use_nodes`` is enabled."""

    def __init__(self, name="Scene"):
        self.name = name
        self._use_nodes = False
        self._node_tree = None

    @property
    def use_nodes(self):
        return self._use_nodes

    @use_nodes.setter
    def use_nodes(self, value):
        self._use_nodes = bool(value)
        if self._use_nodes and self._node_tree is None:
            self._node_tree = FakeNodeTree()

    @property
    def node_tree(self):
        return self._node_tree


class FakeSceneCollection:
    def __init__(self, scenes):
        self._scenes = list(scenes)

    def get(self, name):
        for scene in self._scenes:
            if scene.name == name:
                return scene
        return None

    def __iter__(self):
        return iter(self._scenes)

    def __len__(self):
        return len(self._scenes)


def _bpy_with_scene(scene):
    bpy = make_mock_bpy()
    bpy.context.scene = scene
    bpy.data.scenes = FakeSceneCollection([scene])
    return bpy


def _add_node(node_tree, node):
    node_tree.nodes._nodes.append(node)  # noqa: SLF001 - test fixture shortcut
    return node


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL}/scripts/{script}.py", bpy, **kwargs)


# ---------------------------------------------------------------------------
# Node type catalogue
# ---------------------------------------------------------------------------


def test_resolve_compositor_node_type_accepts_id_label_and_alias():
    assert resolve_compositor_node_type("CompositorNodeDenoise") == "CompositorNodeDenoise"
    assert resolve_compositor_node_type("Denoise") == "CompositorNodeDenoise"
    assert resolve_compositor_node_type("denoise") == "CompositorNodeDenoise"
    assert resolve_compositor_node_type("bloom") == "CompositorNodeGlare"
    assert resolve_compositor_node_type("ShaderNodeTexImage") is None
    assert resolve_compositor_node_type("") is None


def test_list_compositor_node_types_returns_catalog():
    result = _call("list_compositor_node_types", make_mock_bpy())
    assert result["success"] is True
    ids = {entry["id"] for entry in result["context"]["node_types"]}
    assert {"CompositorNodeRLayers", "CompositorNodeComposite", "CompositorNodeDenoise"}.issubset(ids)
    assert "input" in result["context"]["categories"]


def test_list_compositor_node_types_filters_by_category_and_search():
    result = _call("list_compositor_node_types", make_mock_bpy(), category="filter")
    assert result["success"] is True
    assert {entry["category"] for entry in result["context"]["node_types"]} == {"filter"}

    result = _call("list_compositor_node_types", make_mock_bpy(), search="cryptomatte")
    assert result["success"] is True
    assert [entry["id"] for entry in result["context"]["node_types"]] == [
        "CompositorNodeCryptomatte",
        "CompositorNodeCryptomatteV2",
    ]


def test_list_compositor_node_types_rejects_unknown_category():
    result = _call("list_compositor_node_types", make_mock_bpy(), category="nonsense")
    assert result["success"] is False
    assert "unknown" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tree lifecycle
# ---------------------------------------------------------------------------


def test_setup_compositor_tree_enables_and_wires_default_template():
    scene = FakeScene()
    result = _call("setup_compositor_tree", _bpy_with_scene(scene))

    assert result["success"] is True
    assert scene.use_nodes is True
    assert result["context"]["template"] == "default"
    assert result["context"]["created_nodes"] == ["Render Layers", "Composite"]
    assert result["context"]["link"]["from_node"] == "Render Layers"
    assert result["context"]["link"]["to_node"] == "Composite"
    assert len(list(scene.node_tree.links)) == 1


def test_setup_compositor_tree_is_idempotent():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    _call("setup_compositor_tree", bpy)
    result = _call("setup_compositor_tree", bpy)

    assert result["success"] is True
    assert result["context"]["created_nodes"] == []
    assert result["context"]["link"] is None
    assert len(list(scene.node_tree.nodes)) == 2
    assert len(list(scene.node_tree.links)) == 1


def test_setup_compositor_tree_empty_template_creates_nothing():
    scene = FakeScene()
    result = _call("setup_compositor_tree", _bpy_with_scene(scene), template="empty")

    assert result["success"] is True
    assert result["context"]["created_nodes"] == []
    assert result["context"]["link"] is None
    assert len(list(scene.node_tree.nodes)) == 0


def test_setup_compositor_tree_clear_removes_existing_nodes():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    _call("setup_compositor_tree", bpy)
    result = _call("setup_compositor_tree", bpy, clear=True)

    assert result["success"] is True
    assert result["context"]["cleared_nodes"] == 2
    assert len(list(scene.node_tree.nodes)) == 2


def test_setup_compositor_tree_rejects_unknown_template():
    result = _call("setup_compositor_tree", _bpy_with_scene(FakeScene()), template="fancy")
    assert result["success"] is False
    assert "template" in result["message"].lower()


def test_setup_compositor_tree_targets_named_scene():
    scene = FakeScene("Shot_010")
    result = _call("setup_compositor_tree", _bpy_with_scene(scene), scene_name="Shot_010")
    assert result["success"] is True
    assert result["context"]["scene_name"] == "Shot_010"


def test_setup_compositor_tree_rejects_unknown_scene():
    result = _call("setup_compositor_tree", _bpy_with_scene(FakeScene()), scene_name="Missing")
    assert result["success"] is False
    assert "scene not found" in result["message"].lower()


def test_set_compositor_enabled_toggles_use_nodes():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    assert _call("set_compositor_enabled", bpy)["context"]["use_nodes"] is True
    assert _call("set_compositor_enabled", bpy, enabled=False)["context"]["use_nodes"] is False


def test_clear_compositor_tree_removes_every_node():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    _call("setup_compositor_tree", bpy)
    result = _call("clear_compositor_tree", bpy)

    assert result["success"] is True
    assert result["context"]["removed_nodes"] == 2
    assert len(list(scene.node_tree.nodes)) == 0


def test_clear_compositor_tree_requires_enabled_compositor():
    result = _call("clear_compositor_tree", _bpy_with_scene(FakeScene()))
    assert result["success"] is False
    assert "not enabled" in result["message"].lower()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _ready_scene():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    _call("setup_compositor_tree", bpy)
    return scene, bpy


def test_create_compositor_node_by_alias_creates_node():
    scene, bpy = _ready_scene()
    result = _call("create_compositor_node", bpy, node_type="denoise", name="Denoise Pass")

    assert result["success"] is True
    assert result["context"]["node_type"] == "CompositorNodeDenoise"
    assert result["context"]["node"]["name"] == "Denoise Pass"
    assert scene.node_tree.nodes.get("Denoise Pass") is not None


def test_create_compositor_node_accepts_id_label_and_location():
    _scene, bpy = _ready_scene()
    result = _call(
        "create_compositor_node",
        bpy,
        node_type="CompositorNodeGlare",
        name="Bloom",
        location=[300, -40],
    )
    assert result["success"] is True
    assert result["context"]["node"]["location"] == [300.0, -40.0]

    result = _call("create_compositor_node", bpy, node_type="Viewer")
    assert result["success"] is True
    assert result["context"]["node_type"] == "CompositorNodeViewer"


def test_create_compositor_node_enables_compositor_when_disabled():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    result = _call("create_compositor_node", bpy, node_type="math")

    assert result["success"] is True
    assert scene.use_nodes is True


def test_create_compositor_node_rejects_unknown_type():
    _scene, bpy = _ready_scene()
    result = _call("create_compositor_node", bpy, node_type="ShaderNodeTexImage")
    assert result["success"] is False
    assert "unsupported" in result["message"].lower()


def test_create_compositor_node_rejects_duplicate_name():
    _scene, bpy = _ready_scene()
    _call("create_compositor_node", bpy, node_type="blur", name="Blur")
    result = _call("create_compositor_node", bpy, node_type="blur", name="Blur")

    assert result["success"] is False
    assert "already exists" in result["message"].lower()


def test_create_compositor_node_rejects_bad_location():
    _scene, bpy = _ready_scene()
    result = _call("create_compositor_node", bpy, node_type="blur", location=[1, 2, 3])
    assert result["success"] is False
    assert "location" in result["message"].lower()


def test_delete_compositor_node_removes_node():
    scene, bpy = _ready_scene()
    _call("create_compositor_node", bpy, node_type="denoise", name="Denoise Pass")
    result = _call("delete_compositor_node", bpy, node_name="Denoise Pass")

    assert result["success"] is True
    assert scene.node_tree.nodes.get("Denoise Pass") is None


def test_delete_compositor_node_reports_missing_node():
    _scene, bpy = _ready_scene()
    result = _call("delete_compositor_node", bpy, node_name="Ghost")
    assert result["success"] is False
    assert "not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def _scene_with_denoise():
    scene, bpy = _ready_scene()
    _add_node(scene.node_tree, FakeNode("CompositorNodeDenoise", name="Denoise Pass"))
    return scene, bpy


def test_connect_compositor_nodes_links_sockets():
    scene, bpy = _scene_with_denoise()
    _call("disconnect_compositor_nodes", bpy, from_node="Render Layers", to_node="Composite")

    result = _call(
        "connect_compositor_nodes",
        bpy,
        from_node="Render Layers",
        from_socket="Image",
        to_node="Denoise Pass",
        to_socket="Image",
    )
    assert result["success"] is True
    assert result["context"]["link"]["to_node"] == "Denoise Pass"

    result = _call(
        "connect_compositor_nodes",
        bpy,
        from_node="Denoise Pass",
        from_socket="Image",
        to_node="Composite",
        to_socket="Image",
    )
    assert result["success"] is True
    assert len(list(scene.node_tree.links)) == 2


def test_connect_compositor_nodes_reports_unknown_socket():
    _scene, bpy = _scene_with_denoise()
    result = _call(
        "connect_compositor_nodes",
        bpy,
        from_node="Denoise Pass",
        from_socket="Nope",
        to_node="Composite",
        to_socket="Image",
    )
    assert result["success"] is False
    assert "output socket not found" in result["message"].lower()


def test_connect_compositor_nodes_reports_unknown_node():
    _scene, bpy = _scene_with_denoise()
    result = _call(
        "connect_compositor_nodes",
        bpy,
        from_node="Ghost",
        from_socket="Image",
        to_node="Composite",
        to_socket="Image",
    )
    assert result["success"] is False
    assert "node not found" in result["message"].lower()


def test_disconnect_compositor_nodes_by_endpoints_and_id():
    scene, bpy = _ready_scene()
    result = _call("disconnect_compositor_nodes", bpy, from_node="Render Layers", to_node="Composite")
    assert result["success"] is True
    assert result["context"]["count"] == 1
    assert len(list(scene.node_tree.links)) == 0

    _call(
        "connect_compositor_nodes",
        bpy,
        from_node="Render Layers",
        from_socket="Image",
        to_node="Composite",
        to_socket="Image",
    )
    links = _call("list_compositor_node_links", bpy)["context"]["links"]
    result = _call("disconnect_compositor_nodes", bpy, link_id=links[0]["id"])
    assert result["success"] is True
    assert len(list(scene.node_tree.links)) == 0


def test_disconnect_compositor_nodes_requires_criteria():
    _scene, bpy = _ready_scene()
    result = _call("disconnect_compositor_nodes", bpy)
    assert result["success"] is False
    assert "criteria" in result["message"].lower()


def test_disconnect_compositor_nodes_reports_no_match():
    _scene, bpy = _ready_scene()
    result = _call("disconnect_compositor_nodes", bpy, to_node="Ghost")
    assert result["success"] is False
    assert "no matching" in result["message"].lower()


def test_list_compositor_node_links_returns_links():
    _scene, bpy = _ready_scene()
    result = _call("list_compositor_node_links", bpy)

    assert result["success"] is True
    assert result["context"]["count"] == 1
    assert result["context"]["links"][0]["from_node"] == "Render Layers"


def test_list_compositor_node_links_requires_enabled_compositor():
    result = _call("list_compositor_node_links", _bpy_with_scene(FakeScene()))
    assert result["success"] is False
    assert "not enabled" in result["message"].lower()


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def test_set_compositor_node_value_updates_socket():
    scene, bpy = _scene_with_denoise()
    _add_node(scene.node_tree, FakeNode("CompositorNodeBlur", name="Blur"))
    result = _call("set_compositor_node_value", bpy, node_name="Blur", socket="Size X", value=12.5)

    assert result["success"] is True
    assert result["context"]["value"] == 12.5
    assert scene.node_tree.nodes.get("Blur").inputs.get("Size X").default_value == 12.5


def test_set_compositor_node_value_reports_unknown_socket():
    _scene, bpy = _scene_with_denoise()
    result = _call("set_compositor_node_value", bpy, node_name="Denoise Pass", socket="Nope", value=1)
    assert result["success"] is False
    assert "input socket not found" in result["message"].lower()


def test_set_compositor_node_value_flags_linked_sockets():
    scene, bpy = _ready_scene()
    # "Image" on Composite is linked to Render Layers by the default template.
    result = _call(
        "set_compositor_node_value",
        bpy,
        node_name="Composite",
        socket="Image",
        value=[0.1, 0.2, 0.3],
    )
    assert result["success"] is True
    assert result["context"]["is_linked"] is True
    assert result["context"]["value"] == [0.1, 0.2, 0.3, 1.0]


def test_get_compositor_node_value_reads_all_sockets():
    scene, bpy = _scene_with_denoise()
    result = _call("get_compositor_node_value", bpy, node_name="Denoise Pass")

    assert result["success"] is True
    assert [entry["name"] for entry in result["context"]["inputs"]] == ["Image", "Normal", "Albedo"]
    assert [entry["name"] for entry in result["context"]["outputs"]] == ["Image"]


def test_get_compositor_node_value_reads_single_socket():
    scene, bpy = _scene_with_denoise()
    _call("set_compositor_node_value", bpy, node_name="Denoise Pass", socket="Image", value=[0.2, 0.4, 0.6])
    result = _call("get_compositor_node_value", bpy, node_name="Denoise Pass", socket="Image")

    assert result["success"] is True
    assert result["context"]["value"][:3] == [0.2, 0.4, 0.6]


def test_get_compositor_node_value_reports_unknown_node():
    _scene, bpy = _ready_scene()
    result = _call("get_compositor_node_value", bpy, node_name="Ghost")
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_read_tools_do_not_enable_the_compositor():
    scene = FakeScene()
    bpy = _bpy_with_scene(scene)
    result = _call("get_compositor_node_value", bpy, node_name="Composite")

    assert result["success"] is False
    assert scene.use_nodes is False


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_tools():
    doc = yaml.safe_load(Path(COMPOSITOR_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "setup_compositor_tree",
        "set_compositor_enabled",
        "clear_compositor_tree",
        "create_compositor_node",
        "delete_compositor_node",
        "connect_compositor_nodes",
        "disconnect_compositor_nodes",
        "set_compositor_node_value",
        "get_compositor_node_value",
        "list_compositor_node_links",
        "list_compositor_node_types",
    }.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert "annotations" in tool
        source = Path("src/dcc_mcp_blender/skills") / SKILL / tool["source_file"]
        assert source.is_file(), f"missing source script: {source}"


def test_read_only_tools_are_flagged_read_only():
    doc = yaml.safe_load(Path(COMPOSITOR_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    for name in ("get_compositor_node_value", "list_compositor_node_links", "list_compositor_node_types"):
        assert tools[name]["read_only"] is True
        assert tools[name]["annotations"]["read_only_hint"] is True
