"""Plan installation of a downloaded Blender add-on package."""

from __future__ import annotations

from typing import Any, Dict

from dcc_mcp_core.skill import run_main, skill_entry, skill_exception, skill_success

from dcc_mcp_blender.extension_packages import plan_extension_install


@skill_entry
def main(package: Dict[str, Any], **_kwargs: Any) -> dict:
    try:
        plan = plan_extension_install(package)
        return skill_success("Blender add-on installation planned", **plan)
    except Exception as exc:
        return skill_exception(exc, message="Failed to plan Blender add-on installation")


if __name__ == "__main__":
    run_main(main)
