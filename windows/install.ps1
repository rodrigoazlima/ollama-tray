#Requires -Version 5.1
<#
.SYNOPSIS
  Install and optionally auto-start the Ollama system tray app.

.DESCRIPTION
  1. Installs Python dependencies (pystray, Pillow, pywin32, psutil).
  2. Registers autostart in HKCU\...\Run so the tray icon appears at every logon.
     No admin rights required.

.PARAMETER Uninstall
  Remove the OllamaTray autostart entry.

.PARAMETER NoDeps
  Skip pip install step.

.PARAMETER Python
  Python executable to use. Default: "python".

.EXAMPLE
  .\windows\install.ps1              # install deps + register autostart
  .\windows\install.ps1 -Uninstall   # remove autostart
  .\windows\install.ps1 -NoDeps      # skip pip, just register autostart
#>

param(
    [switch]$Uninstall,
    [switch]$NoDeps,
    [string]$Python = "python"
)

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$TaskName   = "OllamaTray"

# ── uninstall ────────────────────────────────────────────────────────────────
if ($Uninstall) {
    Write-Host "Removing autostart entry '$TaskName'..."
    try {
        Remove-ItemProperty `
            -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
            -Name $TaskName `
            -ErrorAction Stop
        Write-Host "  Removed."
    } catch {
        Write-Host "  '$TaskName' not found — nothing to remove."
    }
    exit 0
}

# ── install deps ─────────────────────────────────────────────────────────────
if (-not $NoDeps) {
    Write-Host "Installing Python dependencies..."
    & $Python -m pip install -r "$RepoRoot\requirements.txt" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed. Ensure Python is in PATH or pass -Python <path>."
        exit 1
    }
    Write-Host "  Dependencies OK."
}

# ── register autostart ───────────────────────────────────────────────────────
$PythonPath = (Get-Command $Python -ErrorAction Stop).Source
$Cmd = "`"$PythonPath`" -m ollama_tray"

Write-Host "Registering autostart (HKCU Run / $TaskName)..."
Set-ItemProperty `
    -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name $TaskName `
    -Value $Cmd

Write-Host ""
Write-Host "Installed. Tray icon appears after next logon."
Write-Host "To start now:"
Write-Host "  & `"$PythonPath`" -m ollama_tray"
Write-Host ""
Write-Host "CLI commands:"
Write-Host "  python -m ollama_tray --status     # print service status"
Write-Host "  python -m ollama_tray --start      # start Ollama service  (UAC if needed)"
Write-Host "  python -m ollama_tray --stop       # stop Ollama service   (UAC if needed)"
Write-Host "  python -m ollama_tray --restart    # restart Ollama service"
Write-Host "  python -m ollama_tray --uninstall  # remove autostart"
