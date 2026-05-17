# blender-link-win.ps1
# Create symlinks from source tree into Blender's addons directory for live development
# Usage: just blender-link-win  or  powershell -File tools/blender-link-win.ps1 -BlenderVersion 4.2

param(
    [string]$BlenderVersion = $env:BLENDER_VERSION,
    # tools/ → repository root (dcc-mcp-blender), not the monorepo parent
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

# Default Blender version
if ([string]::IsNullOrEmpty($BlenderVersion)) {
    $BlenderVersion = "4.2"
}

# Detect Blender addons directory
$AppData = $env:APPDATA
$AddonsDir = Join-Path $AppData "Blender Foundation\Blender\$BlenderVersion\scripts\addons"
$Target = Join-Path $AddonsDir "dcc_mcp_blender"

Write-Host "🔗 Setting up Blender dev symlinks (Blender $BlenderVersion)..." -ForegroundColor Cyan
Write-Host "   Project  : $ProjectRoot" -ForegroundColor Gray
Write-Host "   Addons   : $AddonsDir" -ForegroundColor Gray
Write-Host ""

# Create addons dir if needed
if (!(Test-Path $AddonsDir)) {
    New-Item -ItemType Directory -Force -Path $AddonsDir | Out-Null
    Write-Host "   Created addons directory" -ForegroundColor Yellow
}

# Remove old link/dir if exists
if (Test-Path $Target) {
    $targetItem = Get-Item $Target
    if ($targetItem.LinkType) {
        # It's a symlink, remove it
        Remove-Item $Target -Force
        Write-Host "   Removed old symlink" -ForegroundColor Yellow
    } else {
        # It's a real directory
        Write-Host "   ⚠️  $Target is a real directory (not a symlink)." -ForegroundColor Yellow
        Write-Host "   Remove it manually if you want to use dev symlinks." -ForegroundColor Yellow
        exit 1
    }
}

# Source directory
$SourceDir = Join-Path $ProjectRoot "src\dcc_mcp_blender"

if (!(Test-Path -LiteralPath $SourceDir)) {
    Write-Host "   ❌ Source not found: $SourceDir" -ForegroundColor Red
    Write-Host "   Fix: run this script from the dcc-mcp-blender repo (or pass -ProjectRoot)." -ForegroundColor Yellow
    exit 1
}

# Create symbolic link
# Requires developer mode or admin privileges
try {
    New-Item -ItemType SymbolicLink -Path $Target -Target $SourceDir -Force -ErrorAction Stop | Out-Null
    Write-Host "   ✅ Symbolic link created successfully" -ForegroundColor Green
    Write-Host "      $Target → $SourceDir" -ForegroundColor Gray
} catch {
    Write-Host "   ⚠️  Symbolic link failed (need admin or Developer Mode), copying instead..." -ForegroundColor Yellow
    try {
        Copy-Item -Path $SourceDir -Destination $Target -Recurse -Force -ErrorAction Stop
        Write-Host "   ✅ Source copied (edits require manual copy)" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ Copy failed: $_" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "   Next: start Blender $BlenderVersion → Edit → Preferences → Add-ons → Enable 'DCC MCP Blender'" -ForegroundColor Cyan
Write-Host "   Edit source → restart Blender (or press F8 to reload scripts) to see changes." -ForegroundColor Cyan
