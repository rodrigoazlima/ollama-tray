#Requires -Version 5.1
# Build ollama-tray.exe — single file, no console window, Ollama icon embedded.
# Run from repo root or the windows/ subdirectory.
# Output: dist\ollama-tray.exe

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$Src       = Join-Path $RepoRoot "ollama_tray.py"
$Ico       = "$env:LOCALAPPDATA\Programs\Ollama\app.ico"
$Dist      = Join-Path $RepoRoot "dist"
$Build     = Join-Path $RepoRoot "build"

if (-not (Test-Path $Ico)) {
    Write-Warning "Ollama icon not found at $Ico — using PyInstaller default"
    $IconArg = @()
} else {
    $IconArg = @("--icon=$Ico")
}

pyinstaller @IconArg `
    --onefile `
    --noconsole `
    --name="ollama-tray" `
    --distpath="$Dist" `
    --workpath="$Build" `
    --specpath="$RepoRoot" `
    "$Src"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Built:  $Dist\ollama-tray.exe"
    Write-Host "Run:    & '$Dist\ollama-tray.exe'"
    Write-Host "Install autostart with the exe:"
    Write-Host "    & '$Dist\ollama-tray.exe' --install"
}
