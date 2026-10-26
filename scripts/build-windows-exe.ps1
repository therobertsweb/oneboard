$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller pillow

$Logo = "logo.jpeg"
$IconDir = "build-assets"
$Icon = Join-Path $IconDir "logo.ico"

if (-not (Test-Path $Logo)) {
    throw "logo.jpeg was not found in the project root."
}

if (-not (Test-Path $IconDir)) {
    New-Item -ItemType Directory -Path $IconDir | Out-Null
}

& $Python -c "from PIL import Image; img=Image.open('logo.jpeg'); img.save(r'$Icon', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name ONEBoard `
    --icon $Icon `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --add-data "logo.jpeg;." `
    oneboard_desktop.py

Write-Host ""
Write-Host "Build complete: dist\ONEBoard\ONEBoard.exe"
Write-Host "Put .env next to ONEBoard.exe if you want custom HOST, PORT, Google credentials, or site directory."
