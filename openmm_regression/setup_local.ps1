param([string]$PythonCommand = 'py')
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$python = Join-Path $workspace '.venv/Scripts/python.exe'
$wheel = Get-ChildItem -LiteralPath (Join-Path $workspace 'dist') -Filter 'openmm-*+local.*-cp312-cp312-win_amd64.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) { throw 'Dogrulanmis yerel wheel dist klasorunde bulunamadi.' }
if (-not (Test-Path -LiteralPath $python)) {
    & $PythonCommand -3.12 -m venv (Join-Path $workspace '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 sanal ortami olusturulamadi.' }
}
& $python -m pip install --no-index --find-links (Join-Path $workspace 'dist') --force-reinstall $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw 'OpenMM paketi kurulamadi.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Bagimliliklar eksik; proje requirements dosyasindaki NumPy surumunu kurun.' }
Push-Location $PSScriptRoot
try {
    & $python (Join-Path $PSScriptRoot 'test_native.py')
    if ($LASTEXITCODE -ne 0) { throw 'OpenMM regresyon dogrulamasi basarisiz.' }
} finally { Pop-Location }
