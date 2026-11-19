# GameTrans AI - Windows OCR game translator (MVP)

**Status: MVP source code, not yet a verified Windows release.**

GameTrans AI is a standalone Windows game translator; it does not inject code or modify games.

## Features
- Select a running game window as the capture source.
- Screenshot the game client area and drag OCR rectangles in its preview.
- Each game gets a separate saved profile; OCR regions use percentages and resize with its game window.
- Recognize Chinese text with RapidOCR and ONNX Runtime.
- Translate to Vietnamese online via deep-translator's Google provider.
- Cache translations locally in SQLite, reducing repeated provider requests.
- Edit an exact phrase glossary per game.
- Show a click-through overlay clipped to the game client rectangle.
- DXcam with MSS fallback, threaded scans, and approximate frame change detection.

## Windows requirements
Windows 10/11 x64. Game in windowed or borderless mode. An internet connection is needed for translating unseen phrases.

## Run source
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Build executable
Run `build_windows.bat`, or open **GitHub Actions → Build Windows EXE**. It builds on Windows, runs 10 unit tests, and uploads the `GameTransAI-Windows-x64` bundle. Download and extract all files; launch `GameTransAI.exe` in the extracted folder.

## Known limitations
Accuracy cannot be 100% and latency varies. Current game regions need manual setup. OCR is throttled and new text depends on network availability. Fullscreen-exclusive/anti-cheat games may disallow capture or overlays. Multi-monitor/DPI support requires real-world verification. Glossary matches entire phrase, not all terms inside sentences. Some errors still show English. A successful build does not guarantee runtime compatibility with every game.

**Privacy:** Captured text for unseen phrases is sent to a third-party translation provider. Profiles and translation cache stay in your local Windows user data directory.
