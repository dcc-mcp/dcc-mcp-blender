# blender-status-win.ps1
# Show current Blender dev link status
# Usage: just blender-status-win  or  powershell -File tools/blender-status-win.ps1

param(
    [string]$BlenderVersion = $env:BLENDER_VERSION
)

# Default Blender version
if ([string]::IsNullOrEmpty($BlenderVersion)) {
    $BlenderVersion = "4.2"
}

# Detect Blender addons directory
$AppData = $env:APPDATA
$AddonsDir = Join-Path $AppData "Blender Foundation\Blender\$BlenderVersion\scripts\addons"
$Target = Join-Path $AddonsDir "dcc_mcp_blender"

Write-Host "📋 Blender dev link status:" -ForegroundColor Cyan
Write-Host "   Addons dir: $AddonsDir" -ForegroundColor Gray
Write-Host ""

if (Test-Path $Target) {
    $targetItem = Get-Item $Target
    if ($targetItem.LinkType) {
        # It's a symlink
        $linkTarget = Get-Item $Target | Select-Object -ExpandProperty Target
        Write-Host "   ✅ dcc_mcp_blender → $linkTarget (symlink)" -ForegroundColor Green
    } else {
        # It's a real directory
        Write-Host "   ⚠️  dcc_mcp_blender exists (copied, not linked)" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ❌ dcc_mcp_blender not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "   To setup: just blender-link-win" -ForegroundColor Cyan
Write-Host "   To remove: just blender-unlink-win" -ForegroundColor Cyan
