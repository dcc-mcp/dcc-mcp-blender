#!/usr/bin/env python
"""Show Python and dependency versions for dcc-mcp-blender."""

import sys
from importlib.metadata import PackageNotFoundError, version

print("📦 Environment Information:")
print(f"Python version: {sys.version.split()[0]}")
print("")

print("Key Packages:")
packages = ["dcc-mcp-blender", "dcc-mcp-core", "pytest", "ruff"]
for pkg in packages:
    try:
        print(f"  {pkg}: {version(pkg)}")
    except PackageNotFoundError:
        if pkg == "dcc-mcp-blender":
            print(f"  {pkg}: not installed (run: pip install -e .)")
        else:
            print(f"  {pkg}: not installed")
