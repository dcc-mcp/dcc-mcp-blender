# dcc-mcp-blender development justfile
# Unified dependency and task management

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["bash", "-c"]
set dotenv-load := true

# Default recipe
default:
    @just --list

# ============================================================================
# Dependency Management
# ============================================================================

# Install development dependencies
@install-dev:
    echo "🔧 Installing development dependencies..."
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
    echo "✅ Development dependencies installed"

# Install minimal dependencies (production only)
@install-prod:
    echo "🔧 Installing production dependencies..."
    python -m pip install --upgrade pip
    python -m pip install -e .
    echo "✅ Production dependencies installed"

# Install all dependencies (dev + test + build)
@install-all: install-dev
    echo "✅ All dependencies ready"

# Verify dependency installation
@verify-deps:
    echo "🔍 Verifying dependency installation..."
    python -c "from dcc_mcp_blender import start_server; print('✓ dcc_mcp_blender')"
    python -c "from dcc_mcp_core import create_skill_server; print('✓ dcc_mcp_core')"
    python -c "import pytest; print('✓ pytest')"
    python -c "import bpy" 2>/dev/null && echo "✓ bpy (Blender Python)" || echo "⚠️  bpy not available (install in Blender or use blender python)"
    echo "✅ Core dependencies verified"

# ============================================================================
# Linting & Code Quality
# ============================================================================

# Run ruff check on src/ and tests/
@lint:
    echo "🔍 Running ruff lint check..."
    python -m ruff check src/ tests/ tools/lint_skills.py packaging/assemble_zip.py
    echo "✅ Lint check passed"

# Auto-fix ruff errors
@lint-fix:
    echo "🔧 Auto-fixing ruff errors..."
    python -m ruff check --fix src/ tests/ tools/lint_skills.py packaging/assemble_zip.py
    echo "✅ Lint errors fixed"

# Lint SKILL.md files
@lint-skills:
    echo "🔍 Linting SKILL.md files..."
    python tools/lint_skills.py --warnings-as-errors
    echo "✅ SKILL.md lint passed"

# Run all lint checks
lint-all: lint lint-skills
    echo "✅ All lint checks passed"

# Pre-commit gate: auto-fix, format, lint, quick tests.
# Run this before every commit/push to avoid CI failures.
# Usage: vx just prek   or   just prek
@prek:
    echo "🔧 Auto-fixing ruff errors..."
    python -m ruff check --fix src/ tests/ tools/lint_skills.py packaging/assemble_zip.py
    echo "🎨 Formatting with ruff..."
    python -m ruff format src/ tests/ tools/lint_skills.py packaging/assemble_zip.py
    echo "🔍 Running all lint checks..."
    python -m ruff check src/ tests/ tools/lint_skills.py packaging/assemble_zip.py
    python tools/lint_skills.py --warnings-as-errors
    echo "🧪 Running quick tests..."
    python -m pytest tests/ -x -q --ignore=tests/test_e2e_blender_standalone.py 2>/dev/null || python -m pytest tests/ -x -q
    echo "✅ prek passed — safe to commit"

# ============================================================================
# Testing
# ============================================================================

# Run basic import tests
@test-imports:
    echo "🧪 Running import tests..."
    python -m pytest tests/test_basic_imports.py -v 2>/dev/null || echo "⚠️  test_basic_imports.py not found"
    echo "✅ Import tests passed"

# Run all quick tests (no blender required)
@test-quick:
    echo "🧪 Running quick tests..."
    python -m pytest tests/ -x -q
    echo "✅ Quick tests passed"

# Run tests with coverage
@test-coverage:
    echo "🧪 Running tests with coverage..."
    python -m pytest --cov=dcc_mcp_blender --cov-report=term-missing tests/
    echo "✅ Tests complete with coverage report"

# Run specific test file
@test file="tests/test_basic_imports.py":
    python -m pytest {{file}} -v

# ============================================================================
# Development Workflow
# ============================================================================

# Setup development environment (install + verify)
@setup: install-dev verify-deps
    echo "✅ Development environment ready"

# Check code before commit (lint + quick tests)
@check: lint test-quick
    echo "✅ All checks passed - ready to commit"

# Full CI simulation (lint + tests)
@ci: lint-all test-coverage
    echo "✅ CI simulation complete"

# Clean build artifacts
@clean:
    echo "🧹 Cleaning build artifacts..."
    rm -rf build/ dist/ *.egg-info
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    echo "✅ Cleaned"

# Full clean (including test cache)
@clean-all: clean
    echo "🧹 Deep cleaning..."
    rm -rf .pytest_cache .ruff_cache .coverage htmlcov/
    rm -rf tests/.pytest_cache
    echo "✅ Fully cleaned"

# ============================================================================
# Help & Info
# ============================================================================

# Show Python and dependency versions
@versions:
    python tools/show_versions.py

# Show dependency tree
@deps-tree:
    echo "📦 Dependency tree (core packages):"
    python -m pip show dcc-mcp-blender -f 2>/dev/null | grep "Location\|Requires" || echo "dcc-mcp-blender not installed"
    echo ""
    python -m pip show dcc-mcp-core -f | grep "Location\|Requires"

# ============================================================================
# CI/CD Utilities
# ============================================================================

# Install CI dependencies (for GitHub Actions)
@install-ci: install-dev
    echo "✅ CI dependencies ready"

# Run CI checks locally
@run-ci: clean lint-all test-quick
    echo "✅ Local CI checks passed"

# ============================================================================
# Troubleshooting
# ============================================================================

# Diagnose dependency issues
@diagnose:
    echo "🔍 Diagnosing environment..."
    echo ""
    echo "Python version:"
    python --version
    echo ""
    echo "Pip version:"
    python -m pip --version
    echo ""
    echo "Installed packages (key ones):"
    python -m pip list | grep -E "dcc-mcp|pytest|ruff"
    echo ""
    echo "Trying imports:"
    python -c "from dcc_mcp_blender import start_server; print('✓ dcc_mcp_blender imports OK')" 2>&1 || echo "✗ dcc_mcp_blender import failed"
    python -c "from dcc_mcp_core import create_skill_server; print('✓ dcc_mcp_core imports OK')" 2>&1 || echo "✗ dcc_mcp_core import failed"
    echo ""
    echo "✅ Diagnostic complete"

# Reinstall all dependencies from scratch
@reinstall-all: clean-all
    echo "🔧 Removing pip cache..."
    python -m pip cache purge
    echo "🔧 Reinstalling all dependencies..."
    just install-all
    just verify-deps
    echo "✅ Full reinstall complete"

# Fix common dependency issues
@fix-deps:
    echo "🔧 Attempting to fix dependency issues..."
    echo "  - Upgrading pip..."
    python -m pip install --upgrade pip setuptools wheel
    echo "  - Installing core dependencies..."
    python -m pip install -e .
    echo "  - Installing dev dependencies..."
    python -m pip install -e ".[dev]"
    echo "✅ Dependency issues fixed"

# ============================================================================
# Blender Local Development
# ============================================================================

# Blender version for local dev (override: just blender-version=4.2 blender-link)
blender-version := env("BLENDER_VERSION", "4.2")

# Detect Blender scripts directory (platform-aware)
_blender-scripts-dir := if os() == "windows" {
    env("APPDATA", "") + "/Blender Foundation/Blender/" + blender-version + "/scripts"
} else if os() == "macos" {
    env("HOME", "") + "/Library/Application Support/Blender/" + blender-version + "/scripts"
} else {
    env("HOME", "") + "/.config/blender/" + blender-version + "/scripts"
}

# Detect Blender addons directory
_blender-addons-dir := _blender-scripts-dir + "/addons"

# Create symlinks from source tree into Blender's addons directory for live development.
# After running this, enabling the addon in Blender will use your local source code directly —
# edits take effect on next Blender restart (or via F8 reload scripts).
@blender-link:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd || pwd)"
    # On Windows in Git Bash, use the script's real location
    if [ -f "justfile" ]; then PROJECT_ROOT="$(pwd)"; fi

    ADDONS_DIR="{{ _blender-addons-dir }}"
    TARGET="$ADDONS_DIR/dcc_mcp_blender"

    echo "🔗 Setting up Blender dev symlinks (Blender {{ blender-version }})..."
    echo "   Project  : $PROJECT_ROOT"
    echo "   Addons   : $ADDONS_DIR"
    echo ""

    # Create addons dir if needed
    mkdir -p "$ADDONS_DIR"

    # Remove old link/dir if exists
    if [ -L "$TARGET" ]; then
        rm "$TARGET"
        echo "   Removed old symlink"
    elif [ -d "$TARGET" ]; then
        echo "   ⚠️  $TARGET is a real directory (not a symlink)."
        echo "   Remove it manually if you want to use dev symlinks."
        exit 1
    fi

    # Create symlink
    if [ "$(uname -s)" = "MINGW"* ] || [ "$(uname -s)" = "MSYS"* ] || [ -n "${WINDIR:-}" ]; then
        # Windows (Git Bash): use mklink (requires admin or developer mode)
        cmd //c "mklink /D \"$(cygpath -w "$TARGET")\" \"$(cygpath -w "$PROJECT_ROOT/src/dcc_mcp_blender")\"" 2>/dev/null || \
            { echo "   ⚠️  Symlink failed, copying instead..."; cp -r "$PROJECT_ROOT/src/dcc_mcp_blender" "$TARGET"; }
    else
        # Unix: symlinks just work
        ln -sf "$PROJECT_ROOT/src/dcc_mcp_blender" "$TARGET"
    fi

    echo ""
    echo "   ✅ Symlink created:"
    echo "      $TARGET → $PROJECT_ROOT/src/dcc_mcp_blender (live source)"
    echo ""
    echo "   Next: start Blender {{ blender-version }} → Edit → Preferences → Add-ons → Enable 'DCC MCP Blender'"
    echo "   Edit source → restart Blender (or press F8 to reload scripts) to see changes."

# Windows version: Create symlinks using PowerShell (for native Windows without Git Bash)
@blender-link-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-link-win.ps1 -BlenderVersion {{ blender-version }}

# Build a Blender-installable addon ZIP (bundles dcc-mcp-core from PyPI). Output: dist_addon/
# Pick platform from host OS — run with explicit platform: `python packaging/assemble_zip.py --platform win64`
blender-addon-zip:
    python packaging/assemble_zip.py --platform {{ if os() == "windows" { "win64" } else if os() == "macos" { "macos" } else { "linux" } }} --output-dir dist_addon/

# Remove dev symlinks and addon files
@blender-unlink:
    #!/usr/bin/env bash
    set -euo pipefail
    ADDONS_DIR="{{ _blender-addons-dir }}"
    TARGET="$ADDONS_DIR/dcc_mcp_blender"

    echo "🧹 Removing Blender dev symlinks..."

    if [ -d "$TARGET" ]; then
        rm -rf "$TARGET"
        echo "   Removed $TARGET"
    fi

    echo "   ✅ Dev symlinks cleaned up"

# Windows version: Remove dev symlinks using PowerShell
@blender-unlink-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-unlink-win.ps1

# Show current Blender dev link status
@blender-status:
    #!/usr/bin/env bash
    ADDONS_DIR="{{ _blender-addons-dir }}"
    TARGET="$ADDONS_DIR/dcc_mcp_blender"

    echo "📋 Blender dev link status:"
    echo "   Addons dir: $ADDONS_DIR"
    echo ""

    if [ -L "$TARGET" ]; then
        REAL=$(readlink "$TARGET" 2>/dev/null || echo "?")
        echo "   ✅ dcc_mcp_blender → $REAL (symlink)"
    elif [ -d "$TARGET" ]; then
        echo "   ⚠️  dcc_mcp_blender exists (copied, not linked)"
    else
        echo "   ❌ dcc_mcp_blender not found"
    fi

# Windows version: Show Blender dev link status using PowerShell
@blender-status-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-status-win.ps1

# Start Blender with dev addon loaded (Unix/macOS)
@blender-start:
    echo "🚀 Starting Blender {{ blender-version }}..."
    blender || /Applications/Blender.app/Contents/MacOS/Blender || echo "❌ Blender not found in PATH"

# Windows version: Start Blender
@blender-start-win blender-version="{{ blender-version }}":
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& { \
        $$blenderPath = 'C:\Program Files\Blender Foundation\Blender {{ blender-version }}\blender.exe'; \
        if (Test-Path $$blenderPath) { \
            Start-Process $$blenderPath \
        } else { \
            Write-Host '❌ Blender not found at:' $$blenderPath; \
            Write-Host '   Please install Blender or set BLENDER_PATH environment variable' \
        } \
    }"

# Full local dev setup: link + verify
blender-dev: blender-link verify-deps
    @echo ""
    @echo "📋 Dev environment linked. Now start Blender:"
    @echo "   Unix/macOS: just blender-start"
    @echo "   Windows: just blender-start (or use blender-link-win for PowerShell)"
    @echo ""
    @echo "   Then in Blender: Edit → Preferences → Add-ons → Enable 'DCC MCP Blender'"
    @echo ""
    @echo "   Verify with:"
    @echo "     just blender-status       # Unix/macOS"
    @echo "     just blender-status-win   # Windows"

# ============================================================================
# Blender + Core Development (with dcc-mcp-core build)
# ============================================================================

# Windows: build dcc-mcp-core with Blender's Python, then symlink both
# `dcc_mcp_core` (from core's `python/dcc_mcp_core`) and `dcc_mcp_blender` (from `src/dcc_mcp_blender`)
# into Blender's addons directory. Then start Blender for debugging.
#
# After run, use MCP URL printed below; see Blender MCP setup docs for Cursor + debugpy.
# Default core repo: sibling directory `../dcc-mcp-core` or env `DCC_MCP_CORE_REPO`.
#
#   just blender-dev-build-link-core-win
#   just blender-dev-debug-win
#   just blender-version=4.3 blender-dev-debug-win
@blender-dev-build-link-core-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-dev-build-link-core-win.ps1 -BlenderVersion {{ blender-version }}

@blender-dev-debug-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-dev-build-link-core-win.ps1 -BlenderVersion {{ blender-version }} -LaunchBlender

# Windows: only refresh symlinks (skip maturin develop) after you already built core.
@blender-dev-relink-core-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/blender-dev-build-link-core-win.ps1 -BlenderVersion {{ blender-version }} -SkipBuild
