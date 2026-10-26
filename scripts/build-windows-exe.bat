@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m pip install pyinstaller pillow

if not exist "build-assets" mkdir build-assets

".venv\Scripts\python.exe" -c "from PIL import Image; img=Image.open('logo.jpeg'); img.save(r'build-assets\logo.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name ONEBoard --icon "build-assets\logo.ico" --add-data "templates;templates" --add-data "static;static" --add-data "logo.jpeg;." oneboard_desktop.py

echo.
echo Build complete: dist\ONEBoard\ONEBoard.exe
echo Put .env next to ONEBoard.exe if you want custom HOST, PORT, Google credentials, or site directory.
