"""Set the scene world background color and optional strength."""

from __future__ import annotations

from typing import Any, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Blender stores socket colors as 32-bit floats; allow for the round-trip loss.
_COLOR_TOLERANCE = 1e-6


def _coerce_color(color: List[float]) -> List[float]:
    if len(color) not in (3, 4):
        raise ValueError("color must contain 3 or 4 values")
    rgba = list(color[:4])
    if len(rgba) == 3:
        rgba.append(1.0)
    return rgba


def _read_color(socket: Any) -> Optional[List[float]]:
    """Read a color socket back as a list of floats.

    Returns ``None`` when the stored value cannot be interpreted as a color
    (for example on mocked or unexpected socket objects) so callers can skip
    verification instead of reporting a false failure.
    """
    try:
        values = [float(component) for component in socket.default_value]
    except (AttributeError, TypeError, ValueError):
        return None
    return values if len(values) >= 3 else None


def _read_float(socket: Any) -> Optional[float]:
    """Read a float socket back, or None when the value is not readable."""
    try:
        return float(socket.default_value)
    except (AttributeError, TypeError, ValueError):
        return None


def _socket_link_state(socket: Any) -> Optional[bool]:
    """Return the socket's link state, or None when it cannot be determined.

    Only a real ``bool`` counts: mocked or unexpected sockets expose arbitrary
    attributes that must not be mistaken for a link either way. Callers act on
    an explicit ``True``/``False`` and skip the check when this is ``None``.
    """
    state = getattr(socket, "is_linked", None)
    return state if isinstance(state, bool) else None


def _first_output(node: Any) -> Any:
    """Return a node's first output socket, or None when it has none."""
    outputs = getattr(node, "outputs", None)
    if not outputs:
        return None
    return outputs[0]


def _find_node(nodes: Any, node_type: str) -> Any:
    """Return the first node of ``node_type``, or None."""
    for node in nodes:
        if getattr(node, "type", None) == node_type:
            return node
    return None


def _ensure_background_node(world: Any) -> Any:
    """Return the world's ``ShaderNodeBackground``, creating it when missing.

    Enabling ``use_nodes`` makes Blender materialise the default node tree, but
    a world can also carry a node tree with no background node at all (or an
    empty one), so the node is looked up first and created as a fallback.
    """
    world.use_nodes = True
    node_tree = world.node_tree
    nodes = node_tree.nodes

    background = _find_node(nodes, "BACKGROUND")
    if background is not None:
        return background

    # Nothing to drive the surface yet: build the standard Background -> Output
    # chain so the color we are about to write actually reaches the renderer.
    background = nodes.new("ShaderNodeBackground")
    output = _find_node(nodes, "OUTPUT_WORLD")
    if output is None:
        output = nodes.new("ShaderNodeOutputWorld")
    node_tree.links.new(background.outputs[0], output.inputs["Surface"])
    return background


def set_world_background(
    color: List[float],
    strength: Optional[float] = None,
) -> dict:
    """Set scene world background color.

    Args:
        color: RGB or RGBA values in the 0-1 range.
        strength: Optional world shader strength when nodes are available.

    Returns:
        ActionResultModel dict.
    """
    try:
        import bpy

        rgba = _coerce_color(color)
        scene = bpy.context.scene
        world = scene.world
        if world is None:
            world = bpy.data.worlds.new(name="World")
            scene.world = world

        # ``world.color`` drives the non-node path (and the viewport display).
        # It is set first because Blender seeds a freshly created node tree from
        # it, but it is NOT enough on its own: once the node tree exists the
        # background node keeps its own value, so the socket is written below.
        world.color = rgba[:3]

        node_tree = getattr(world, "node_tree", None)
        if strength is None and node_tree is None and not getattr(world, "use_nodes", False):
            # No node tree in play, so ``world.color`` already is the value the
            # renderer reads. Switching the world over to nodes here would be a
            # silent change the caller never asked for.
            return skill_success(
                "World background updated",
                color=rgba,
                strength=strength,
                prompt="World background updated. Render the scene to review environment lighting.",
            )

        background = _ensure_background_node(world)
        color_socket = background.inputs["Color"]

        # A linked socket keeps accepting ``default_value`` writes, but the link
        # wins at evaluation time, so the write would be a no-op for the render.
        if _socket_link_state(color_socket) is True:
            return skill_error(
                "World background color is driven by a link",
                "ShaderNodeBackground.Color is connected to another node, so its default value "
                "cannot change the rendered background",
                possible_solutions=[
                    "Remove the link feeding ShaderNodeBackground.Color, then set the color again.",
                    "Or drive the linked node instead (for example an Environment Texture).",
                ],
                color=rgba,
                strength=strength,
            )

        # An isolated background node never reaches the world output either.
        if _socket_link_state(_first_output(background)) is False:
            return skill_error(
                "World background node is not connected to the output",
                "ShaderNodeBackground is not linked into ShaderNodeOutputWorld.Surface, so it "
                "cannot affect the rendered background",
                possible_solutions=[
                    "Link the background node's Background output to the World Output Surface input.",
                ],
                color=rgba,
                strength=strength,
            )

        color_socket.default_value = rgba

        # Guard against a wrapped success: only report success when the value
        # actually landed in the socket. Unreadable sockets skip the check.
        applied_color = _read_color(color_socket)
        if applied_color is not None and not all(
            abs(applied - requested) <= _COLOR_TOLERANCE for applied, requested in zip(applied_color, rgba)
        ):
            return skill_error(
                "World background color was not applied",
                "ShaderNodeBackground.Color is {0} after writing {1}".format(
                    [round(value, 6) for value in applied_color], rgba
                ),
                possible_solutions=[
                    "Check whether the background Color socket is driven by a driver.",
                    "Remove the driver, then set the world background color again.",
                ],
                color=rgba,
                strength=strength,
            )

        if strength is not None:
            # No legacy fallback: a Background node always owns a Strength
            # socket, so a missing one is a real error rather than something to
            # paper over with a non-existent ``world.strength`` property.
            strength_socket = background.inputs["Strength"]
            strength_socket.default_value = float(strength)

            applied_strength = _read_float(strength_socket)
            if applied_strength is not None and abs(applied_strength - float(strength)) > _COLOR_TOLERANCE:
                return skill_error(
                    "World background strength was not applied",
                    "ShaderNodeBackground.Strength is {0} after writing {1}".format(
                        round(applied_strength, 6), float(strength)
                    ),
                    possible_solutions=[
                        "Check whether the background Strength socket is driven by a link or a driver.",
                    ],
                    color=rgba,
                    strength=strength,
                )

        return skill_success(
            "World background updated",
            color=rgba,
            strength=strength,
            prompt="World background updated. Render the scene to review environment lighting.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except ValueError as exc:
        return skill_error("Invalid world background color", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to set world background")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_world_background`."""
    return set_world_background(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
