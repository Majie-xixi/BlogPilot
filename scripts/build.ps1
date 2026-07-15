$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m unittest discover -s tests -p 'test_*.py' -v
python -m PyInstaller --noconfirm --clean BlogPostPublisher.spec
Write-Host "Built: $root\dist\BlogPostPublisher.exe"
