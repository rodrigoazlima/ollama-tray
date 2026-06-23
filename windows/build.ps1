#Requires -Version 5.1
# Build ollama-tray.exe — single file, no console window, Ollama icon embedded.
# Run from repo root or the windows/ subdirectory.
# Output: dist\ollama-tray.exe

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$Spec      = Join-Path $ScriptDir "ollama-tray.spec"
$Dist      = Join-Path $RepoRoot "dist"
$Build     = Join-Path $RepoRoot "build"

pyinstaller "$Spec" --distpath="$Dist" --workpath="$Build"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Built:  $Dist\ollama-tray.exe"
    Write-Host "Run:    & '$Dist\ollama-tray.exe'"
    Write-Host "Install autostart:"
    Write-Host "    & '$Dist\ollama-tray.exe' --install"
}
