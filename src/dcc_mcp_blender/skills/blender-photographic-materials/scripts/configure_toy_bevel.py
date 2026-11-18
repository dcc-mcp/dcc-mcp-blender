"""Configure the millimetre-scale bevel used by photographic toy shots."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_material_ops import configure_toy_bevel


@skill_entry
def main(**kwargs) -> dict:
    return configure_toy_bevel(**kwargs)


if __name__ == "__main__":
    run_main(main)
