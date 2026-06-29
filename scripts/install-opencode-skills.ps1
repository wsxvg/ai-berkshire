#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install AI Berkshire OpenCode skills.
.DESCRIPTION
    Generates OpenCode-compatible skill packages from skills/*.md,
    then installs them to $env:HOME\.opencode\skills\.
#>

$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$DEST = if ($env:OPENCODE_SKILLS_DIR) {
    $env:OPENCODE_SKILLS_DIR
} else {
    Join-Path $env:USERPROFILE ".opencode\skills"
}

Write-Host "AI Berkshire – OpenCode Skill Installer"
Write-Host "Source: $ROOT"
Write-Host "Dest:   $DEST"
Write-Host ""

# Step 1: Sync (generate OpenCode format)
Write-Host "[1/3] Generating OpenCode skills from skills/*.md ..."
python (Join-Path $ROOT "scripts\sync-opencode-skills.py")
if (-not $?) {
    Write-Error "Sync failed"
    exit 1
}

# Step 2: Ensure destination exists
Write-Host "[2/3] Ensuring destination directory ..."
New-Item -ItemType Directory -Path $DEST -Force | Out-Null

# Step 3: Copy each skill
Write-Host "[3/3] Installing skills ..."
$SRC = Join-Path $ROOT "opencode-skills"
$count = 0
Get-ChildItem -Path $SRC -Directory | ForEach-Object {
    $name = $_.Name
    $target = Join-Path $DEST $name
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
    }
    Copy-Item -Recurse -Path $_.FullName -Destination $target
    $count++
    Write-Host "  Installed: $name"
}

# Make tools executable (no-op on Windows, for consistency)
Write-Host ""
Write-Host "Installed $count skills to $DEST"
Write-Host "Restart OpenCode to pick up new skills."
