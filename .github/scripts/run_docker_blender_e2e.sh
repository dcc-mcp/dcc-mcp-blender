#!/usr/bin/env bash
set -euo pipefail

workspace="${GITHUB_WORKSPACE:-/workspace}"
temp_dir="${RUNNER_TEMP:-/tmp}"

BLENDER_BIN=$(command -v blender || find /usr /opt /app -type f -name blender 2>/dev/null | head -1)
if [ -z "${BLENDER_BIN:-}" ]; then
  echo "Unable to locate blender in image"
  exit 1
fi

BLENDER_PYTHON=$(find /usr /opt /app -path "*/python/bin/python3*" -type f 2>/dev/null | head -1)
if [ -z "${BLENDER_PYTHON:-}" ]; then
  BLENDER_PYTHON=$(command -v python3 || true)
fi
if [ -z "${BLENDER_PYTHON:-}" ]; then
  echo "Unable to locate Python in image"
  exit 1
fi

"$BLENDER_BIN" --version
"$BLENDER_PYTHON" --version

PYTHON_INSTALLER="$BLENDER_PYTHON"
if ! "$PYTHON_INSTALLER" -m pip --version >/dev/null 2>&1; then
  "$PYTHON_INSTALLER" -m ensurepip --upgrade || true
fi
if ! "$PYTHON_INSTALLER" -m pip --version >/dev/null 2>&1; then
  get_pip="$temp_dir/get-pip.py"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$get_pip"
  elif command -v wget >/dev/null 2>&1; then
    wget -q https://bootstrap.pypa.io/get-pip.py -O "$get_pip"
  fi
  if [ -f "$get_pip" ]; then
    "$PYTHON_INSTALLER" "$get_pip" --break-system-packages || "$PYTHON_INSTALLER" "$get_pip" || true
  fi
fi
if ! "$PYTHON_INSTALLER" -m pip --version >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    rm -f /etc/apt/sources.list.d/*nodesource*
    apt-get update
    apt-get install -y python3-pip
    PYTHON_INSTALLER=$(command -v python3)
  else
    echo "Unable to install pip in image"
    exit 1
  fi
fi

dep_dir="$temp_dir/blender-e2e-site"
mkdir -p "$dep_dir"
PIP_BREAK_SYSTEM_PACKAGES=1 "$PYTHON_INSTALLER" -m pip install --upgrade --target "$dep_dir" "$workspace[dev]"
PYTHONPATH="$dep_dir:$workspace/src" "$PYTHON_INSTALLER" -c "from dcc_mcp_core import _core; print('dcc-mcp-core _core loaded OK')"

export BLENDER_E2E_SITE="$dep_dir"
"$BLENDER_BIN" --background --python "$workspace/.github/scripts/run_blender_e2e.py"
