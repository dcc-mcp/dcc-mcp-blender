"""List Blender light rigs."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import list_light_rigs


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_light_rigs`."""
    return list_light_rigs(**kwargs)


if __name__ == "__main__":
    run_main(main)
