# GKA final original-source audit: one owner-facing PowerShell command.
# Execute inside a trusted extracted GKA_WINDOWS_LOCAL_BUNDLE directory:
# pwsh -NoProfile -File .\scripts\GKA_FINAL_WINDOWS.ps1
param(
    [string]$OutputDir = ""
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Script = Join-Path $Root 'research\gka_final_owner_replay.py'
if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    throw "The portable GKA replay file is missing: $Script"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $OutputDir = Join-Path $env:USERPROFILE "Documents\GKA_FINAL_PROOF_$Stamp"
}
$Launcher = Get-Command 'py' -ErrorAction SilentlyContinue
if ($Launcher) {
    & py -3 $Script --output-dir $OutputDir
} else {
    $Python = Get-Command 'python' -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "Python 3.11+ is required. Install Python and re-run without changing any saved data."
    }
    & python $Script --output-dir $OutputDir
}
if ($LASTEXITCODE -ne 0) {
    throw "Original source replay was NOT accepted. Inspect GKA_FINAL_REPLAY_STATUS.json and logs in $OutputDir"
}
Write-Host "ORIGINAL SOURCE COMPUTATIONAL REPLAY SUCCESS"
Write-Host "Evidence directory: $OutputDir"
Write-Host "This is NOT a physical battery fault, capacity or SoH certification."
