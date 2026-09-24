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

        background = _ensure_background_node(world)
        background.inputs["Color"].default_value = rgba

        # Guard against a wrapped success: only report success when the value
        # actually landed in the socket. Unreadable sockets skip the check.
        applied_color = _read_color(background.inputs["Color"])
        if applied_color is not None and not all(
            abs(applied - requested) <= _COLOR_TOLERANCE for applied, requested in zip(applied_color, rgba)
        ):
            return skill_error(
                "World background color was not applied",
                "ShaderNodeBackground.Color is {0} after writing {1}".format(
                    [round(value, 6) for value in applied_color], rgba
                ),
                possible_solutions=[
                    "Check whether the background Color socket is driven by a link or a driver.",
                    "Remove the link or driver, then set the world background color again.",
                ],
                color=rgba,
                strength=strength,
            )

        if strength is not None:
            if "Strength" in background.inputs:
                background.inputs["Strength"].default_value = float(strength)
            else:
                world.strength = float(strength)

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
