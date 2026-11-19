@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Please install Python 3.12 and try again.
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
python -m PyInstaller --clean --noconfirm --onedir --windowed --name GameTransAI --collect-all rapidocr --collect-all onnxruntime --collect-all dxcam --collect-data cv2 main.py
if errorlevel 1 exit /b 1
echo.
echo SUCCESS: dist\GameTransAI\GameTransAI.exe
echo Keep ALL files in dist\GameTransAI together.
endlocal
