param([string]$PythonCommand = 'py')
$ErrorActionPreference = 'Stop'

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dist = Join-Path $workspace 'dist'
$venv = Join-Path $workspace '.venv'
$python = Join-Path $venv 'Scripts/python.exe'
$runtimePython = Join-Path $workspace '.runtime312/python.exe'
$recordPath = Join-Path $PSScriptRoot 'native_results/wheel.json'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'

# Prefer the accessible, project-local runtime; fall back to a registered 3.12.
if (Test-Path -LiteralPath $runtimePython) {
    $basePython = $runtimePython
} else {
    $probe = & $PythonCommand -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $probe) {
        throw 'CPython 3.12 is required. Install it or restore .runtime312, then rerun this script.'
    }
    $basePython = ($probe | Select-Object -Last 1).Trim()
}

$pythonVersion = & $basePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne '3.12') {
    throw "Expected CPython 3.12, got '$pythonVersion'."
}

# Repair stale Store-backed venv metadata without deleting installed packages.
if (Test-Path -LiteralPath $venv) {
    & $basePython -m venv --upgrade $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not refresh the existing virtual environment from CPython 3.12.' }
    $cfg = Join-Path $venv 'pyvenv.cfg'
    if (Test-Path -LiteralPath $cfg) {
        $contents = Get-Content -LiteralPath $cfg
        $baseHome = Split-Path -Parent $basePython
        $contents = $contents | ForEach-Object {
            if ($_ -match '^home\s*=') { "home = $baseHome" }
            elseif ($_ -match '^executable\s*=') { "executable = $basePython" }
            elseif ($_ -match '^command\s*=') { "command = $basePython -m venv $venv" }
            else { $_ }
        }
        $contents | Set-Content -LiteralPath $cfg -Encoding ascii
    }
} else {
    & $basePython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the CPython 3.12 virtual environment.' }
}

$venvVersion = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $venvVersion.Trim() -ne '3.12') {
    throw 'The project virtual environment is not runnable as CPython 3.12.'
}

# Pin the exact locally built binary by both filename and SHA-256.
$wheelRecord = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$wheel = Join-Path $dist $wheelRecord.file
if (-not (Test-Path -LiteralPath $wheel)) {
    throw "Verified wheel is missing: $wheel. Restore the workspace dist directory."
}
$actualHash = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $wheelRecord.sha256.ToLowerInvariant()) {
    throw "Wheel SHA-256 mismatch. Expected $($wheelRecord.sha256); got $actualHash."
}

function Invoke-OpenMMPython {
    param([string]$Label, [string[]]$Arguments)
    Write-Host "`n=== $Label ==="
    $logPath = Join-Path $PSScriptRoot "native_results/$Label.log"
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $argumentLine = ($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
        $process = Start-Process -FilePath $python -ArgumentList $argumentLine -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $exitCode = $process.ExitCode
        $output = @()
        if (Test-Path -LiteralPath $stdoutPath) { $output += Get-Content -LiteralPath $stdoutPath }
        if (Test-Path -LiteralPath $stderrPath) { $output += Get-Content -LiteralPath $stderrPath }
        $output | Set-Content -LiteralPath $logPath -Encoding utf8
        $output | ForEach-Object { Write-Host $_ }
    } finally {
        Remove-Item -LiteralPath $stdoutPath,$stderrPath -Force -ErrorAction SilentlyContinue
    }
    if ($exitCode -ne 0) { throw "$Label failed with exit code $exitCode." }
}

Invoke-OpenMMPython 'install' @('-m', 'pip', 'install', '--no-index', '--find-links', $dist, '--force-reinstall', '-r', $requirements)
Invoke-OpenMMPython 'pip_check' @('-m', 'pip', 'check')
Invoke-OpenMMPython 'apply_mmcif_fixes' @((Join-Path $PSScriptRoot 'apply_mmcif_fixes.py'))
Invoke-OpenMMPython 'installation_test' @('-m', 'openmm.testInstallation')
Invoke-OpenMMPython 'mmcif_roundtrip' @((Join-Path $PSScriptRoot 'openmm_mmcif_roundtrip_regression.py'), '--output', (Join-Path $PSScriptRoot 'native_results/mmcif_roundtrip.json'))
Invoke-OpenMMPython 'regressions' @((Join-Path $PSScriptRoot 'test_native.py'))
Invoke-OpenMMPython 'manifest' @((Join-Path $PSScriptRoot 'make_manifest.py'))

Write-Host "`nOpenMM setup and all regression checks passed. Interpreter: $python"
