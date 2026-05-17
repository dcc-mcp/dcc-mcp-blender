"""Set the scene world background color and optional strength."""

from __future__ import annotations

from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _coerce_color(color: List[float]) -> List[float]:
    if len(color) not in (3, 4):
        raise ValueError("color must contain 3 or 4 values")
    rgba = list(color[:4])
    if len(rgba) == 3:
        rgba.append(1.0)
    return rgba


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

        world.color = rgba[:3]

        if strength is not None:
            world.use_nodes = True
            nodes = getattr(getattr(world, "node_tree", None), "nodes", [])
            background = None
            for node in nodes:
                if getattr(node, "type", None) == "BACKGROUND":
                    background = node
                    break
            if background is not None and "Strength" in background.inputs:
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
