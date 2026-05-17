# Build dcc-mcp-core with the target Blender's Python, then link core + dcc-mcp-blender into
# Blender's addons directory for live debugging (no wheel copy).
#
# Prerequisites: Rust (cargo) on PATH, Git, optional vx on PATH for stubgen fallback.
#
# Usage:
#   .\tools\blender-dev-build-link-core-win.ps1 -BlenderVersion 4.2
#   .\tools\blender-dev-build-link-core-win.ps1 -BlenderVersion 4.2 -CoreRepo G:\path\to\dcc-mcp-core
#   .\tools\blender-dev-build-link-core-win.ps1 -BlenderVersion 4.2 -LaunchBlender
#
# Environment:
#   DCC_MCP_CORE_REPO — override path to dcc-mcp-core (default: sibling of this git repo)
#
# Blender bundles its own Python. We use this Python to build dcc-mcp-core with maturin develop,
# then symlink both dcc_mcp_core and dcc_mcp_blender into Blender's addons directory.

param(
    [string]$BlenderVersion = "4.2",
    [string]$CoreRepo = "",
    [switch]$SkipBuild,
    [switch]$LaunchBlender
)

$ErrorActionPreference = "Stop"

$BlenderRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $BlenderRoot) {
    $BlenderRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $CoreRepo) {
    if ($env:DCC_MCP_CORE_REPO) {
        $CoreRepo = $env:DCC_MCP_CORE_REPO
    } else {
        $sibling = Join-Path (Split-Path $BlenderRoot -Parent) "dcc-mcp-core"
        if (Test-Path (Join-Path $sibling "Cargo.toml")) {
            $CoreRepo = $sibling
        }
    }
}
if (-not $CoreRepo -or -not (Test-Path (Join-Path $CoreRepo "Cargo.toml"))) {
    Write-Error "dcc-mcp-core not found. Clone it next to dcc-mcp-blender or set DCC_MCP_CORE_REPO / -CoreRepo."
}

$CoreRepo = (Resolve-Path $CoreRepo).Path

# Detect Blender's bundled Python
# Blender 4.x typically uses Python 3.11 or 3.12
$BlenderExe = "C:\Program Files\Blender Foundation\Blender $BlenderVersion\blender.exe"
$BlenderPython = ""

# Try to find Python in Blender directory
if (Test-Path $BlenderExe) {
    # Try common Python version paths
    $blenderDir = Split-Path $BlenderExe -Parent
    $pythonDir = Get-ChildItem -Path (Split-Path $blenderDir -Parent) -Directory | 
                 Where-Object { $_.Name -match '^\d+\.\d+$' } | 
                 Select-Object -First 1
    
    if ($pythonDir) {
        $pythonPath = Join-Path $pythonDir.FullName "python.exe"
        if (Test-Path $pythonPath) {
            $BlenderPython = $pythonPath
        }
    }
    
    # Fallback: try to find python in Blender's directory
    if (-not $BlenderPython) {
        $BlenderBase = Split-Path (Split-Path $BlenderExe -Parent) -Parent
        $BlenderPython = Get-ChildItem -Path $BlenderBase -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | 
                        Select-Object -First 1 -ExpandProperty FullName
    }
} else {
    Write-Host "   ⚠️  Blender $BlenderVersion not found at $BlenderExe" -ForegroundColor Yellow
    Write-Host "   Will use system Python for build" -ForegroundColor Yellow
}

# If Blender Python not found, use system Python
if (-not $BlenderPython -or -not (Test-Path $BlenderPython)) {
    Write-Host "   ⚠️  Blender Python not found, using system python" -ForegroundColor Yellow
    $BlenderPython = "python"
}

$PyTag = & $BlenderPython -c "import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))" 2>$null
if (-not $PyTag) {
    Write-Host "   ⚠️  Failed to get Python version, using default features" -ForegroundColor Yellow
    $PyTag = "3.11"
}

Write-Host "   Detected Python $PyTag (from $BlenderPython)" -ForegroundColor Gray

# Features for maturin develop
$OptFeatures = "workflow,scheduler,prometheus,job-persist-sqlite"
if ([version]$PyTag -ge [version]"3.8") {
    $DevFeatures = "python-bindings,ext-module,abi3-py38,$OptFeatures"
    Write-Host "   Features: DEV + abi3-py38 (stable ABI)" -ForegroundColor Gray
} else {
    $DevFeatures = "python-bindings,ext-module,$OptFeatures"
    Write-Host "   Features: DEV (no abi3)" -ForegroundColor Gray
}

Write-Host "=== dcc-mcp-core (maturin develop via Blender Python) ===" -ForegroundColor Cyan
Write-Host "   Core repo : $CoreRepo"
Write-Host "   Python    : $BlenderPython"
Write-Host ""

if (-not $SkipBuild) {
    Push-Location $CoreRepo
    try {
        Write-Host "   Running stub_gen (cargo)..." -ForegroundColor Gray
        & cargo run -q --bin stub_gen --features stub-gen
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   ⚠️  stub_gen failed (exit $LASTEXITCODE); continuing — run manually in core if needed" -ForegroundColor Yellow
        }

        & $BlenderPython -m pip install -q --upgrade pip
        & $BlenderPython -m pip install -q maturin

        $coreNativeDir = Join-Path $CoreRepo "python\dcc_mcp_core"
        Get-ChildItem -Path $coreNativeDir -Filter "_core*.pyd" -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "   Removing stale $($_.Name) before rebuild" -ForegroundColor Gray
            Remove-Item $_.FullName -Force
        }

        Write-Host "   maturin develop --features $DevFeatures ..." -ForegroundColor Gray
        & $BlenderPython -m maturin develop --features $DevFeatures
        if ($LASTEXITCODE -ne 0) { throw "maturin develop failed" }

        # Build the standalone dcc-mcp-server binary for sidecar mode
        Write-Host "   cargo build --release -p dcc-mcp-server ..." -ForegroundColor Gray
        & cargo build --release -p dcc-mcp-server
        if ($LASTEXITCODE -ne 0) { throw "cargo build dcc-mcp-server failed" }
    } finally {
        Pop-Location
    }

    $corePkg = Join-Path $CoreRepo "python\dcc_mcp_core"
    if (-not (Test-Path $corePkg)) {
        Write-Error "Expected package dir missing after build: $corePkg"
    }
    Write-Host "   ✅ dcc_mcp_core built under $corePkg" -ForegroundColor Green
} else {
    Write-Host "   SkipBuild: not rebuilding core" -ForegroundColor Yellow
}

# Resolve the sidecar binary path
$ServerBin = Join-Path $CoreRepo "target\release\dcc-mcp-server.exe"
if (-not (Test-Path $ServerBin)) {
    Write-Host "   ⚠️  dcc-mcp-server.exe not found at $ServerBin" -ForegroundColor Yellow
    $ServerBin = $null
} else {
    Write-Host "   ✅ dcc-mcp-server binary at $ServerBin" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Blender addon link (core + blender) ===" -ForegroundColor Cyan

# Blender addons directory
$AddonsDir = Join-Path $env:APPDATA "Blender Foundation\Blender\$BlenderVersion\scripts\addons"
$Target = Join-Path $AddonsDir "dcc_mcp_blender"
$PkgBlender = Join-Path $BlenderRoot "src\dcc_mcp_blender"
$PkgCore = Join-Path $CoreRepo "python\dcc_mcp_core"

if (-not (Test-Path $PkgBlender)) { Write-Error "Missing $PkgBlender" }
if (-not $SkipBuild -and -not (Test-Path $PkgCore)) { Write-Error "Missing $PkgCore — build core first (remove -SkipBuild)" }

New-Item -ItemType Directory -Force -Path $AddonsDir | Out-Null
if (Test-Path $Target) {
    Remove-Item $Target -Recurse -Force
    Write-Host "   Removed old $Target" -ForegroundColor Gray
}

New-Item -ItemType Directory -Force -Path $Target | Out-Null

# Create symbolic links
$linkBlender = Join-Path $Target "dcc_mcp_blender"
$linkCore = Join-Path $Target "dcc_mcp_core"

# For addons, we need to put source directly in addons/dcc_mcp_blender/
# Actually, Blender expects the addon to be a directory containing __init__.py
# So we link the source directory as the addon directory

try {
    # Remove if exists
    if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
    
    # Create symlink for dcc_mcp_blender (the entire package)
    New-Item -ItemType SymbolicLink -Path $Target -Target $PkgBlender -ErrorAction Stop | Out-Null
    Write-Host "   ✅ $Target → $PkgBlender" -ForegroundColor Green
} catch {
    Write-Error "Symlink dcc_mcp_blender failed (enable Windows Developer Mode or run elevated): $_"
}

# For dcc_mcp_core, we need it in Blender's Python sys.path
# Option 1: Create a .pth file in addons directory
# Option 2: Create a symlink in the addons directory
# Let's use option 2 for consistency

$coreLinkPath = Join-Path $AddonsDir "dcc_mcp_core"
try {
    if (Test-Path $coreLinkPath) { Remove-Item $coreLinkPath -Recurse -Force }
    New-Item -ItemType SymbolicLink -Path $coreLinkPath -Target $PkgCore -ErrorAction Stop | Out-Null
    Write-Host "   ✅ $coreLinkPath → $PkgCore" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️  Cannot symlink dcc_mcp_core, will create .pth file" -ForegroundColor Yellow
    
    # Create .pth file to add core to sys.path
    $pthPath = Join-Path $AddonsDir "dcc_mcp_core.pth"
    $PkgCore | Out-File -FilePath $pthPath -Encoding ASCII
    Write-Host "   ✅ Created $pthPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Start Blender $BlenderVersion → Edit → Preferences → Add-ons → Enable 'DCC MCP Blender'." -ForegroundColor Cyan
Write-Host ""
Write-Host "MCP (Streamable HTTP, default):" -ForegroundColor Cyan
Write-Host "   http://127.0.0.1:8765/mcp"
Write-Host "Docs: See dcc-mcp-blender docs for Cursor/Bender MCP setup" -ForegroundColor Gray

if ($LaunchBlender) {
    if (Test-Path $BlenderExe) {
        Write-Host "Launching $BlenderExe ..." -ForegroundColor Cyan
        Start-Process -FilePath $BlenderExe
    } else {
        Write-Host "   ⚠️  Blender not found at $BlenderExe" -ForegroundColor Yellow
    }
}
