$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = Join-Path $root 'src'
$staleExecutable = Join-Path $root 'dist\BlogPostPublisher.exe'
if (Test-Path -LiteralPath $staleExecutable) {
    Remove-Item -LiteralPath $staleExecutable -Force
}
python -m unittest discover -s tests -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --noconfirm --clean BlogPostPublisher.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$privateMarker = Join-Path $root 'dist\blogpilot-data-dir.txt'
if (Test-Path -LiteralPath $privateMarker) {
    Remove-Item -LiteralPath $privateMarker -Force
}
$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts\build_msi.py --dist dist --version $version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Built: $root\dist\BlogPilot.exe"
Write-Host "Built: $root\dist\BlogPilot-Setup-$version.msi"
