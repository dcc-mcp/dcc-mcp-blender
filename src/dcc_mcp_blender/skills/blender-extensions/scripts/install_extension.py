"""Install a downloaded Blender add-on package."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dcc_mcp_core.skill import run_main, skill_entry, skill_exception, skill_success

from dcc_mcp_blender.extension_packages import install_extension_package


@skill_entry
def main(
    package: Dict[str, Any],
    repository: Optional[str] = None,
    enable: bool = False,
    overwrite: bool = False,
    **_kwargs: Any,
) -> dict:
    try:
        result = install_extension_package(package, repository, enable, overwrite)
        return skill_success("Blender add-on package installed", **result)
    except Exception as exc:
        return skill_exception(exc, message="Failed to install Blender add-on package")


if __name__ == "__main__":
    run_main(main)
