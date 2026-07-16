$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = Join-Path $root 'src'
python -m unittest discover -s tests -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --noconfirm --clean BlogPostPublisher.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$dataMarker = Join-Path $root 'blogpilot-data-dir.txt'
if (Test-Path -LiteralPath $dataMarker) {
    Copy-Item -LiteralPath $dataMarker -Destination (Join-Path $root 'dist\blogpilot-data-dir.txt') -Force
}
Write-Host "Built: $root\dist\BlogPostPublisher.exe"
