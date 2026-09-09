"""Geometric and host failure contracts for solid architectural arches."""

from collections import Counter
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_blender._architectural_mesh import create_pointed_arch, pointed_arch_geometry


@pytest.mark.parametrize("segments", [2, 16, 128])
def test_arch_is_closed_consistently_wound_and_has_real_depth(segments):
    verts, faces = pointed_arch_geometry(2, 3, 1.5, 0.35, 0.8, segments)
    edges = Counter()
    directed = Counter()
    volume = 0
    for face in faces:
        assert len(set(face)) == 4
        for a, b in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directed[(a, b)] += 1
        a = verts[face[0]]
        for i in range(1, len(face) - 1):
            b, c = verts[face[i]], verts[face[i + 1]]
            volume += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                + a[1] * (b[2] * c[0] - b[0] * c[2])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6
    assert set(edges.values()) == {2}
    assert all(directed[(b, a)] == count for (a, b), count in directed.items())
    assert volume > 0  # Outward normals, not merely consistent winding.
    assert len(verts) - len(edges) + len(faces) == 2
    assert max(v[0] for v in verts) - min(v[0] for v in verts) == pytest.approx(2.7)
    assert max(v[1] for v in verts) == pytest.approx(0.8)
    assert min(v[1] for v in verts) == 0
    assert max(v[2] for v in verts) == pytest.approx(4.85)
    # No threshold face closes the actual door opening.
    assert not any(
        all(verts[i][2] == 0 for i in face) and min(verts[i][0] for i in face) < 0 < max(verts[i][0] for i in face)
        for face in faces
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("width", 0),
        ("depth", -1),
        ("rise", float("nan")),
        ("frame_width", float("inf")),
        ("segments", 129),
        ("segments", True),
        ("location", [1, 2]),
        ("location", [0, float("nan"), 0]),
    ],
)
def test_invalid_input_never_creates_blender_data(field, value):
    args = dict(name="Arch", width=2, spring_height=3, rise=1.5, frame_width=0.35, depth=0.8)
    args[field] = value
    bpy = MagicMock()
    with patch.dict("sys.modules", bpy=bpy):
        result = create_pointed_arch(**args)
    assert result["success"] is False
    bpy.data.meshes.new.assert_not_called()


def test_existing_name_does_not_overwrite():
    bpy = MagicMock()
    with patch.dict("sys.modules", bpy=bpy):
        result = create_pointed_arch("Arch", 2, 3, 1.5, 0.35, 0.8)
    assert result["success"] is False
    bpy.data.meshes.new.assert_not_called()


def test_creation_error_removes_owned_mesh():
    bpy = MagicMock()
    bpy.data.objects.get.return_value = None
    bpy.data.meshes.new.return_value.from_pydata.side_effect = RuntimeError("injected failure")
    with patch.dict("sys.modules", bpy=bpy):
        result = create_pointed_arch("Arch", 2, 3, 1.5, 0.35, 0.8)
    assert result["success"] is False
    bpy.data.meshes.remove.assert_called_once_with(bpy.data.meshes.new.return_value)
