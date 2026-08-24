"""Stable facade for Blender's bounded cross-DCC modeling verbs.

The implementation is split by host responsibility; this module remains the
single import surface used by bundled skill scripts and compatibility callers.
"""

from __future__ import annotations

from dcc_mcp_blender._modeling_modifiers import array_instances, boolean_op, delete_history, mirror
from dcc_mcp_blender._modeling_primitives import create_primitive, lathe_profile, loft_sections
from dcc_mcp_blender._modeling_scene import (
    assign_material,
    auto_uv,
    freeze_transforms,
    group_parent,
    set_pivot,
    uv_project,
)
from dcc_mcp_blender._modeling_topology import add_edge_loop, bevel_edges, extrude_faces, inset

__all__ = [
    "add_edge_loop",
    "array_instances",
    "assign_material",
    "auto_uv",
    "bevel_edges",
    "boolean_op",
    "create_primitive",
    "delete_history",
    "extrude_faces",
    "freeze_transforms",
    "group_parent",
    "inset",
    "lathe_profile",
    "loft_sections",
    "mirror",
    "set_pivot",
    "uv_project",
]
