# blender-unlink-win.ps1
# Remove dev symlinks and addon files
# Usage: just blender-unlink-win  or  powershell -File tools/blender-unlink-win.ps1

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

Write-Host "🧹 Removing Blender dev symlinks..." -ForegroundColor Cyan

# Remove target directory/link
if (Test-Path $Target) {
    $targetItem = Get-Item $Target
    if ($targetItem.LinkType) {
        # It's a symlink
        Remove-Item $Target -Force
        Write-Host "   Removed symbolic link: $Target" -ForegroundColor Green
    } else {
        # It's a real directory
        Remove-Item $Target -Recurse -Force
        Write-Host "   Removed directory: $Target" -ForegroundColor Green
    }
} else {
    Write-Host "   Target not found: $Target" -ForegroundColor Yellow
}

Write-Host "   ✅ Dev symlinks cleaned up" -ForegroundColor Green
