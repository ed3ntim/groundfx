# SPDX-License-Identifier: GPL-3.0-or-later
# One-liner to run the GroundFX headless test suite on Windows.
#
#   powershell -File dev\run_tests.ps1
#
# Override the Blender path with -Blender "C:\path\to\blender.exe".
param(
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "GroundFX tests via $Blender"
& $Blender --background --factory-startup --python (Join-Path $repo "tests\run_all.py")
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "All tests passed." -ForegroundColor Green
} else {
    Write-Host "Tests FAILED (exit $code)." -ForegroundColor Red
}
exit $code
