"""V2 desktop UI: select a game, press Start; no OCR region drawing required."""
from __future__ import annotations

import copy
import sys
import traceback

import numpy as np
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from .capture import capture_game
from .models import GameProfile
from .overlay import TranslationOverlay
from .scanner import ScanEngine
from .storage import ProfileStore, TranslationCache
from .translator import Translator
from .windows import game_client_rect, is_game_foreground, list_game_windows

STYLE = """
QWidget { background: #111d2e; color: #e7eff9; font: 10pt 'Segoe UI'; }
QMainWindow { background: #091322; }
QGroupBox { border: 1px solid #334b62; border-radius: 10px; margin-top: 15px;
            padding: 13px 9px 9px 9px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QComboBox, QPlainTextEdit { border: 1px solid #375773; border-radius: 8px;
  padding: 9px; background: #1a2c43; selection-background-color: #147c9d; }
QPushButton { background: #087497; border: 1px solid #37c9e7; border-radius: 8px;
  padding: 10px; font-weight: bold; }
QPushButton:hover { background: #148fad; }
QPushButton:disabled { background: #293b4b; color: #7f91a2; border: 1px solid #293b4b; }
QPushButton#start { background: #00a1ad; color: white; font-size: 12pt; padding: 15px; }
QLabel#heading { font-size: 22pt; font-weight: bold; color: #62e6f3; }
QLabel#status { color: #a4ecca; }
QLabel#hint { color: #a6bed2; }
QLabel#preview { border: 1px solid #2f5169; border-radius: 8px; background: #050d19; }
"""


class GamePreview(QLabel):
    def __init__(self):
        super().__init__("Chọn cửa sổ game để xem trước")
        self.setObjectName("preview")
        self.setMinimumSize(500, 290)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source = None

    def set_frame(self, frame):
        frame = np.ascontiguousarray(frame[:, :, :3])
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self._source = QPixmap.fromImage(image)
        self._redraw()

    def _redraw(self):
        if self._source is not None:
            self.setPixmap(self._source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()


class ScanSignals(QObject):
    finished = Signal(object, int)
    failed = Signal(str, int)


class ScanTask(QRunnable):
    def __init__(self, engine, hwnd, profile, epoch):
        super().__init__()
        self.engine, self.hwnd, self.profile, self.epoch = engine, hwnd, copy.deepcopy(profile), epoch
        self.signals = ScanSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            self.signals.finished.emit(self.engine.scan(self.hwnd, self.profile), self.epoch)
        except Exception:
            self.signals.failed.emit(traceback.format_exc(limit=5), self.epoch)


class GameTransWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameTrans AI V2 - Dịch game Trung sang Việt")
        self.resize(1130, 760)
        self.profiles_store = ProfileStore()
        self.profiles = self.profiles_store.load()
        self.profile = GameProfile("Game mới", "")
        self.cache = TranslationCache()
        self.engine = ScanEngine(Translator(self.cache))
        self.overlay = TranslationOverlay()
        self.windows = []
        self.hwnd = None
        self.running = False
        self.busy = False
        self.task = None
        self.epoch = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._last_geometry = None
        self._build_ui()
        self.refresh_windows()
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_once)
        self.anchor_timer = QTimer(self)
        self.anchor_timer.timeout.connect(self.update_overlay_anchor)
        self.anchor_timer.start(100)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 16, 18, 16)
        title = QLabel("GameTrans AI V2")
        title.setObjectName("heading")
        outer.addWidget(title)
        tip = QLabel("Việt hóa chữ Trung trên toàn bộ cửa sổ game — không cần khoanh vùng OCR")
        tip.setObjectName("hint")
        outer.addWidget(tip)

        cols = QHBoxLayout()
        outer.addLayout(cols, 1)
        left = QFrame()
        lv = QVBoxLayout(left)
        source = QGroupBox("1. Chọn game đang chạy")
        sv = QVBoxLayout(source)
        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.on_window_selected)
        sv.addWidget(self.window_select)
        refresh = QPushButton("Làm mới danh sách game")
        refresh.clicked.connect(self.refresh_windows)
        sv.addWidget(refresh)
        lv.addWidget(source)

        visual = QGroupBox("2. Xem trước màn hình game")
        vv = QVBoxLayout(visual)
        self.preview = GamePreview()
        vv.addWidget(self.preview, 1)
        snap = QPushButton("Chụp thử màn hình game")
        snap.clicked.connect(self.capture_preview)
        vv.addWidget(snap)
        lv.addWidget(visual, 1)

        results = QGroupBox("Nhận diện và bản dịch gần nhất")
        rs = QVBoxLayout(results)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(152)
        self.log.setPlaceholderText("Các cụm tiếng Trung được tự động phát hiện sẽ hiển thị tại đây.")
        rs.addWidget(self.log)
        lv.addWidget(results)
        cols.addWidget(left, 1)

        right = QFrame()
        right.setFixedWidth(320)
        rv = QVBoxLayout(right)
        opts = QGroupBox("Cấu hình tự động")
        ov = QVBoxLayout(opts)
        for label in ["OCR toàn màn hình game", "Dịch từng cụm chữ đúng tọa độ", "Tự co giãn khi thay đổi độ phân giải", "Ưu tiên bộ nhớ dịch SQLite"]:
            v = QLabel("✓  " + label)
            v.setStyleSheet("color:#b9f2e7")
            ov.addWidget(v)
        self.focus_only = QCheckBox("Chỉ hiện khi game đang được chọn")
        self.focus_only.setChecked(True)
        self.focus_only.toggled.connect(self.update_overlay_anchor)
        ov.addWidget(self.focus_only)
        self.overlay_enabled = QCheckBox("Hiển thị tiếng Việt đè trong game")
        self.overlay_enabled.setChecked(True)
        self.overlay_enabled.toggled.connect(self.update_overlay_anchor)
        ov.addWidget(self.overlay_enabled)
        rv.addWidget(opts)
        termgroup = QGroupBox("Từ điển tên riêng (tùy chọn)")
        tv = QVBoxLayout(termgroup)
        tv.addWidget(QLabel("Mỗi dòng: 词语 = Bản dịch tiếng Việt"))
        self.glossary_edit = QPlainTextEdit()
        self.glossary_edit.setPlaceholderText("魂师 = Hồn Sư\n魂环 = Hồn Hoàn")
        self.glossary_edit.setMaximumHeight(115)
        tv.addWidget(self.glossary_edit)
        save = QPushButton("Lưu thuật ngữ")
        save.clicked.connect(self.save_profile)
        tv.addWidget(save)
        rv.addWidget(termgroup)

        self.start_btn = QPushButton("▶ BẮT ĐẦU DỊCH TỰ ĐỘNG")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.start)
        rv.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■ DỪNG DỊCH")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        rv.addWidget(self.stop_btn)
        self.counter = QLabel("Đã lưu: 0 câu dịch")
        rv.addWidget(self.counter)
        self.info = QLabel("Lưu ý: câu chưa có trong bộ nhớ cần Internet.\nGame có chống quay màn hình có thể không tương thích.")
        self.info.setWordWrap(True)
        self.info.setObjectName("hint")
        rv.addWidget(self.info)
        rv.addStretch(1)
        cols.addWidget(right)
        self.status_label = QLabel("Sẵn sàng — chọn game rồi bấm BẮT ĐẦU DỊCH TỰ ĐỘNG")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

    def status(self, msg):
        self.status_label.setText(msg)

    def refresh_windows(self):
        selected = self.hwnd
        name = self.profile.window_title
        self.windows = list_game_windows()
        self.window_select.blockSignals(True)
        self.window_select.clear()
        for win in self.windows:
            self.window_select.addItem(win.title[:85], win.hwnd)
        ix = next((i for i, win in enumerate(self.windows) if win.hwnd == selected), -1)
        if ix < 0:
            ix = next((i for i, win in enumerate(self.windows) if win.title == name), -1)
        if ix >= 0:
            self.window_select.setCurrentIndex(ix)
        self.window_select.blockSignals(False)
        self.on_window_selected(self.window_select.currentIndex())

    def on_window_selected(self, index):
        hwnd = self.window_select.itemData(index) if index >= 0 else None
        if hwnd is None:
            self.hwnd = None
            self.start_btn.setEnabled(False)
            return
        if self.running and hwnd != self.hwnd:
            self.stop()
        self.hwnd = int(hwnd)
        name = next((win.title for win in self.windows if win.hwnd == hwnd), "Game")
        self.profile = self.profiles.get(name, GameProfile(name, name))
        self.glossary_edit.setPlainText("\n".join(f"{k} = {v}" for k, v in self.profile.glossary.items()))
        self.counter.setText(f"Đã lưu: {self.cache.count(self.profile.name):,} câu dịch")
        self.start_btn.setEnabled(not self.running)

    def save_profile(self):
        if not self.hwnd:
            return
        terms = {}
        for line in self.glossary_edit.toPlainText().splitlines():
            if "=" in line:
                source, target = line.split("=", 1)
                if source.strip() and target.strip():
                    terms[source.strip()] = target.strip()
        self.profile.glossary = terms
        self.profiles[self.profile.name] = self.profile
        self.profiles_store.save(self.profiles)
        self.status("Đã lưu thuật ngữ cho game này.")

    def capture_preview(self):
        if not self.hwnd:
            self.status("Chưa chọn cửa sổ game.")
            return
        try:
            frame, rect = capture_game(self.hwnd)
            self.preview.set_frame(frame)
            self.status(f"Đã chụp vùng game: {rect[2]} × {rect[3]} px.")
        except Exception as exc:
            self.status(f"Không chụp được game: {exc}")

    def start(self):
        if not self.hwnd or game_client_rect(self.hwnd) is None:
            QMessageBox.warning(self, "Chưa chọn game", "Hãy mở game ở chế độ cửa sổ hoặc không viền rồi chọn lại.")
            return
        self.save_profile()
        self.epoch += 1
        if not self.busy:
            self.engine.reset()
        self.running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.scan_timer.start(450)
        self.scan_once()
        self.status("Đang tự động dịch chữ trên toàn bộ màn hình game. Quay lại game để xem bản dịch.")

    def stop(self):
        self.epoch += 1
        self.running = False
        self.scan_timer.stop()
        self.start_btn.setEnabled(bool(self.hwnd))
        self.stop_btn.setEnabled(False)
        self.overlay.hide()
        self.overlay.set_results([])
        self.status("Đã dừng dịch.")

    def scan_once(self):
        if self.busy or not self.running or self.hwnd is None:
            return
        if game_client_rect(self.hwnd) is None:
            self.status("Game đã thu nhỏ hoặc đóng. Hãy mở lại game.")
            return
        self.busy = True
        self.task = ScanTask(self.engine, self.hwnd, self.profile, self.epoch)
        self.task.signals.finished.connect(self.scan_done)
        self.task.signals.failed.connect(self.scan_failed)
        self.pool.start(self.task)

    def scan_done(self, result, epoch):
        self.busy = False
        self.task = None
        if epoch != self.epoch or result["hwnd"] != self.hwnd or not self.running:
            return
        current = game_client_rect(self.hwnd)
        if current is None:
            self.overlay.hide()
            return
        if current[2:] != result["geometry"][2:]:
            self.overlay.set_results([])  # Never draw stale text on a resized game.
            self.scan_once()
            return
        self.preview.set_frame(result["image"])
        self.overlay.set_results(result["blocks"], (result["geometry"][2], result["geometry"][3]))
        self.log.setPlainText("\n\n".join(
            f"{b.source}  →  {b.target}  ({b.origin})" for b in result["blocks"]
        ) or "Chưa tìm thấy chữ Trung.")
        self.counter.setText(f"Đã lưu: {self.cache.count(self.profile.name):,} câu dịch")
        if result["errors"]:
            self.status(f"{len(result['blocks'])} cụm dịch, lỗi: {result['errors'][0][:110]}")
        else:
            self.status(f"Đang dịch: {len(result['blocks'])} cụm chữ | lần quét {result['elapsed_ms']} ms | {current[2]}×{current[3]}")
        self.update_overlay_anchor()

    def scan_failed(self, message, epoch):
        self.busy = False
        self.task = None
        if epoch != self.epoch:
            return
        self.overlay.set_results([])
        self.status("Lỗi quét: " + message.splitlines()[-1][:180])

    def update_overlay_anchor(self):
        if not self.running or not self.hwnd or not self.overlay_enabled.isChecked():
            self.overlay.hide()
            return
        rect = game_client_rect(self.hwnd)
        if rect is None or (self.focus_only.isChecked() and not is_game_foreground(self.hwnd)):
            self.overlay.hide()
            return
        x, y, w, h = rect
        if self.overlay.geometry().getRect() != (x, y, w, h):
            self.overlay.setGeometry(x, y, w, h)
            if self._last_geometry is not None and self._last_geometry[2:] != (w, h):
                self.overlay.set_results([])
            self._last_geometry = rect
        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.update()

    def closeEvent(self, event):
        self.stop()
        self.overlay.close()
        self.engine.close()
        event.accept()


def launch_app():
    from .windows import enable_dpi_awareness
    if sys.platform != "win32":
        raise RuntimeError("GameTrans AI V2 requires Windows 10/11")
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    ui = GameTransWindow()
    ui.show()
    return app.exec()
