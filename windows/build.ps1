#Requires -Version 5.1
# Build ollama-tray.exe and setup.exe.
# Run from repo root or the windows/ subdirectory.
# Output: dist\ollama-tray.exe, dist\setup.exe

$ScriptDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot      = Split-Path -Parent $ScriptDir
$Spec          = Join-Path $ScriptDir "ollama-tray.spec"
$SetupSpec     = Join-Path $ScriptDir "setup.spec"
$Dist          = Join-Path $RepoRoot "dist"
$Build         = Join-Path $RepoRoot "build"

pyinstaller "$Spec" --distpath="$Dist" --workpath="$Build"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

pyinstaller "$SetupSpec" --distpath="$Dist" --workpath="$Build"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Built:  $Dist\ollama-tray.exe"
Write-Host "        $Dist\setup.exe"
Write-Host ""
Write-Host "Distribute both files together."
Write-Host "Users run setup.exe to install dependencies and start the tray."
