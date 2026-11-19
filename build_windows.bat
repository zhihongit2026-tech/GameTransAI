@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
set GAMETRANS_OCR_INTEGRATION=1
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
python -m PyInstaller --clean --noconfirm --onedir --windowed --name GameTransAI --collect-all rapidocr --collect-all onnxruntime --collect-all dxcam --collect-data cv2 main.py
if errorlevel 1 exit /b 1
if not exist dist\GameTransAI\GameTransAI.exe exit /b 1
start "" /wait dist\GameTransAI\GameTransAI.exe --ocr-self-test tests\fixtures\douluo_settings.jpg.b64
if errorlevel 1 exit /b 1
echo Build V2 and bundled real screenshot OCR test SUCCESS.
echo Open dist\GameTransAI\GameTransAI.exe (keep the entire folder).
endlocal
