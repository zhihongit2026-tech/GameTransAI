# GameTrans Smart AI V3 — Chinese → Vietnamese directly on top of Windows games

**V3 is a beta, not a game patch.** The program is an external screen-capture and transparent text overlay. It cannot guarantee 100% recognition, perfect text erasure, or compatibility with all fullscreen / anti-cheat games. It does not inject into game processes or modify Lua/bytecode files.

## One-click use

1. Extract the full `GameTransAI-V3-Windows-x64` artifact into a folder (keep the `_internal` directory).
2. Run `GameTransAI.exe` on Windows 10/11 x64; open your game in windowed/borderless mode.
3. Select the game window (e.g. 斗罗大陆：诛邪传说). Translation begins automatically and the launcher hides into the notification tray. Right-click the tray icon to pause, resume, restore settings or quit.
4. Chinese text is recognized anywhere in the **game client area**. Vietnamese appears as a click-through overlay over the original text. The background is approximately reconstructed by small-area inpainting. Actual pixels of the game are NOT changed.
5. When you move or resize the game window, the overlay tracks its client area. The app uses 500-ms scan ticks with a separate translation queue; the actual latency depends on OCR, CPU, and model performance.

## Offline translation setup (important)

**A Windows EXE cannot provide arbitrary offline Chinese→Vietnamese translation without the weights of a translation model.** V3 ships the RapidOCR model, an editable built-in set of game UI terms, and compatibility with your persisted SQLite translations / imported Translation Memory. To translate previously unseen sentences *offline*, install [Ollama](https://ollama.com/download/windows), run `ollama pull qwen2.5:3b` once while connected to the Internet, and keep Ollama running locally. The app uses `http://127.0.0.1:11434/api/generate`. Ollama and its multi-GB model are **not bundled** into the GitHub artifact. CPU-only machines may be slow, especially for many short labels. Game-specific TM is strongly recommended.

You can **Nhập Translation Memory** from a UTF-8 `.tsv`, `.txt`, or `.csv` file. Supported line examples:

```
魂师\tHồn Sư
魂环 = Hồn Hoàn
获得奖励 => Nhận phần thưởng
```

Here `\t` indicates a tab; actual TSV files must use a real tab. Exact matching uses normalized whitespace. TM imports into the currently selected profile or the global `*` profile when no game is selected. It is persisted in `%LOCALAPPDATA%/GameTransAI/translations.sqlite3`. V3 checks profile TM, global TM, prior V3 translations, some legacy V2 Google translations, built-in UI terms, offline Ollama, then **optionally** the online provider.

**Online fallback is OFF by default.** Only enable it if you consent to sending recognized game text to the third-party translation provider. Online requests are gated to approximately one every 2.2 s, automatically pause after 429/`Too many requests`, and retry later rather than issuing an uncontrolled burst. **No script bypasses rate limits.**

## Features and limitations

- RapidOCR detects Chinese labels and returns individual bounding boxes (no manual ROI drawing).
- Background translation futures prevent OCR from waiting for Google or a local LLM; a maximum of 48 phrases may be pending.
- OCR uses full-screen initial detection and incremental changed tiles; on large scene changes it scans the full client. Bright/decorative moving backgrounds can still make scanning costly.
- Text is visually replaced by sampling / inpainting the captured background under the original OCR line, then drawing Vietnamese at the corresponding coordinates. The approximation may look imperfect on textured/moving interfaces.
- The overlay is clipped to the game client area, usually hides when game isn't foreground, tracks movement/resize, and does not intercept mouse input. Windows display capture exclusion is attempted, not guaranteed on every GPU/game.
- If no Ollama model, TM hit or built-in term exists, new text remains Chinese; the program explains that offline translation is unavailable instead of claiming 100% translation.
- To inspect issues, restore the launcher from the tray icon. GameTrans does not screen-record in the background.

## Build and test

Python 3.12 on Windows:

```
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py
```

GitHub Actions `Build Windows EXE V3` executes unit tests, **real RapidOCR on the submitted 斗罗大陆 settings screenshot**, PyInstaller `onedir`, bundled EXE OCR self-test, and an offscreen Qt startup smoke test, then publishes `GameTransAI-V3-Windows-x64` if all succeed. A passing CI build **does not** prove in-game rendering is compatible with your GPU/game: test it in the actual Windows game and send screenshots or logs for defects.


## V3.1: no Vietnamese visible in the game

If the game is captured but no translated overlay appears, inspect the local AI status in the launcher.
**The EXE does NOT include the multi-GB Ollama model.** Install Ollama on Windows,
run `ollama pull qwen2.5:3b`, and use **Kiểm tra AI offline (Ollama)**.
Without a local model or imported TM, only known UI and game labels translate.
Google's unofficial endpoint may return 429; enabling online does not guarantee
service. The app now queues online calls in order and displays cached/TM/known
labels immediately even during throttling. Use the local model for unseen text.

The included built-in glossary covers the screenshot UI: `控制` → Khống chế,
`毒系` → Hệ Độc, `魔法` → Ma pháp, `重新共鸣` → Cộng hưởng lại,
`武魂融合` → Dung hợp Võ Hồn. This is **not** universal game translation.
