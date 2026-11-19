"""PySide6 desktop UI: choose game, mark normalized OCR regions, launch live overlay."""
import copy
import sys
import time
import traceback
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QColor, QBrush, QImage, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QComboBox, QLineEdit, QPushButton,
    QPlainTextEdit, QListWidget, QCheckBox, QMessageBox, QGroupBox,
    QVBoxLayout, QHBoxLayout, QSplitter, QApplication, QFrame,
)
from .models import GameProfile, NormalizedRect, REGION_LABELS
from .storage import ProfileStore, TranslationCache
from .windows import list_game_windows, game_client_rect, is_game_foreground
from .capture import capture_game
from .translator import Translator
from .scanner import ScanEngine
from .overlay import TranslationOverlay
from .language import tr

COLORS = {"dialogue": "#ef68b1", "name": "#f7c343", "items": "#b78cff", "subtitle": "#4de6a8"}
STYLE = """
QWidget { background: #111b2a; color: #e9f2fa; font: 10pt 'Segoe UI'; }
QMainWindow { background: #0c1421; }
QGroupBox { border: 1px solid #304560; border-radius: 10px; margin-top: 13px;
           padding: 12px 7px 7px 7px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget { border: 1px solid #324963;
  border-radius: 6px; padding: 6px; background: #192a40; selection-background-color: #176b88; }
QPushButton { background: #176680; border: 1px solid #20a4c9; border-radius: 7px;
  padding: 8px; font-weight: bold; }
QPushButton:hover { background: #238aac; }
QPushButton:disabled { background: #2a3848; color: #8393a3; border: 1px solid #384657; }
QCheckBox { padding: 4px; }
QLabel#appTitle { font-size: 21pt; font-weight: 800; color: #5be9fc; }
QLabel#status { color: #70edd0; }
"""


class Preview(QWidget):
    edited = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(470, 320)
        self.setMouseTracking(True)
        self.image = None
        self.regions = {}
        self.selected_region = "dialogue"
        self.display = QRectF()
        self.anchor = None
        self.cursor = None

    def set_frame(self, frame):
        import numpy as np
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        self.image = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self.update()

    def set_profile(self, profile):
        self.regions = {key: NormalizedRect.from_dict(v.as_dict()) for key, v in profile.regions.items()}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#07111e"))
        if self.image is None:
            painter.setPen(QColor("#a4c6d7"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             tr("Select a game window, then click CAPTURE PREVIEW"))
            painter.end()
            return
        iw, ih = self.image.width(), self.image.height()
        scale = min(self.width() / iw, self.height() / ih)
        dw, dh = iw * scale, ih * scale
        self.display = QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh)
        painter.drawImage(self.display, self.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for key, r in self.regions.items():
            selected = key == self.selected_region
            color = QColor(COLORS[key])
            pen = QPen(color, 3 if selected else 1.5)
            painter.setPen(pen)
            if selected:
                fill = QColor(color)
                fill.setAlpha(42)
                painter.setBrush(QBrush(fill))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            box = QRectF(self.display.x() + r.x * dw, self.display.y() + r.y * dh,
                         r.w * dw, r.h * dh)
            painter.drawRoundedRect(box, 5, 5)
            painter.setPen(color)
            painter.drawText(box.x() + 6, box.y() + 15, tr(REGION_LABELS[key]))
        if self.anchor is not None and self.cursor is not None:
            box = QRectF(self.anchor, self.cursor).normalized()
            painter.setPen(QPen(QColor("#f2f7fa"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
        painter.end()

    def _normalized_point(self, point):
        if self.display.isNull():
            return None
        if not self.display.contains(point):
            return None
        x = max(0, min(1, (point.x() - self.display.x()) / self.display.width()))
        y = max(0, min(1, (point.y() - self.display.y()) / self.display.height()))
        return QPointF(x, y)

    def mousePressEvent(self, event):
        if self.image is not None and event.button() == Qt.MouseButton.LeftButton:
            if self._normalized_point(event.position()) is not None:
                self.anchor = event.position()
                self.cursor = event.position()

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.cursor = QPointF(
                max(self.display.left(), min(self.display.right(), event.position().x())),
                max(self.display.top(), min(self.display.bottom(), event.position().y())),
            )
            self.update()

    def mouseReleaseEvent(self, event):
        if self.anchor is not None and self.cursor is not None:
            begin = self._normalized_point(self.anchor)
            end = self._normalized_point(self.cursor)
            if begin is not None and end is not None and abs(begin.x() - end.x()) > .01 and abs(begin.y() - end.y()) > .01:
                x, y = min(begin.x(), end.x()), min(begin.y(), end.y())
                r = NormalizedRect(x, y, abs(begin.x() - end.x()), abs(begin.y() - end.y()))
                self.regions[self.selected_region] = r
                self.edited.emit(self.selected_region, r)
            self.anchor = self.cursor = None
            self.update()


class ScanSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ScanTask(QRunnable):
    def __init__(self, engine, hwnd, profile):
        super().__init__()
        self.engine, self.hwnd, self.profile = engine, hwnd, copy.deepcopy(profile)
        self.signals = ScanSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            self.signals.finished.emit(self.engine.scan(self.hwnd, self.profile))
        except Exception:
            self.signals.failed.emit(traceback.format_exc(limit=4))


class GameTransWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameTrans AI - Real-time game translation")
        self.resize(1450, 820)
        self.store = ProfileStore()
        self.profiles = self.store.load()
        self.profile = next(iter(self.profiles.values()), GameProfile("My first game", ""))
        self.cache = TranslationCache()
        self.engine = ScanEngine(Translator(self.cache))
        self.windows = []
        self.hwnd = None
        self.running = False
        self.busy = False
        self.task = None
        self.overlay = TranslationOverlay()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._build_ui()
        self.refresh_windows()
        self.refresh_profiles()
        self.load_profile()
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_once)
        self.anchor_timer = QTimer(self)
        self.anchor_timer.timeout.connect(self.update_overlay_anchor)
        self.anchor_timer.start(120)

    def _button(self, title, callback):
        item = QPushButton(tr(title))
        item.clicked.connect(callback)
        return item

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        header = QHBoxLayout()
        label = QLabel(tr("GameTrans AI"))
        label.setObjectName("appTitle")
        header.addWidget(label)
        header.addWidget(QLabel(tr("Chinese to Vietnamese | Client-anchored capture and overlay")))
        header.addStretch(1)
        v.addLayout(header)

        middle = QHBoxLayout()
        v.addLayout(middle, 1)
        left = QFrame()
        left.setFixedWidth(272)
        lv = QVBoxLayout(left)
        g1 = QGroupBox(tr("Game profiles"))
        gg = QVBoxLayout(g1)
        self.profile_list = QListWidget()
        self.profile_list.currentTextChanged.connect(self.choose_profile)
        gg.addWidget(self.profile_list)
        gg.addWidget(self._button("+ NEW FROM WINDOW", self.new_profile))
        lv.addWidget(g1, 1)
        g2 = QGroupBox(tr("Current profile"))
        cf = QVBoxLayout(g2)
        cf.addWidget(QLabel(tr("Profile name")))
        self.profile_name = QLineEdit()
        cf.addWidget(self.profile_name)
        cf.addWidget(QLabel(tr("Edit capture region (drag in preview)")))
        self.region_select = QComboBox()
        for key, title in REGION_LABELS.items():
            self.region_select.addItem(tr(title), key)
        self.region_select.currentIndexChanged.connect(self.select_region)
        cf.addWidget(self.region_select)
        self.enable_region = QCheckBox(tr("Enable selected OCR region"))
        self.enable_region.toggled.connect(self.toggle_region)
        cf.addWidget(self.enable_region)
        cf.addWidget(self._button("SAVE PROFILE", self.save_profile))
        lv.addWidget(g2)
        middle.addWidget(left)

        center = QFrame()
        cv = QVBoxLayout(center)
        cv.addWidget(QLabel(tr("GAME PREVIEW  /  Drag the colored region to change its OCR area")))
        self.preview = Preview()
        self.preview.edited.connect(self.on_region_edited)
        cv.addWidget(self.preview, 1)
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(self._button("CAPTURE PREVIEW", self.capture_preview))
        preview_buttons.addWidget(self._button("SCAN ONCE", self.scan_once))
        preview_buttons.addWidget(QLabel(tr("Regions scale with the game window size")))
        cv.addLayout(preview_buttons)
        log_group = QGroupBox(tr("Last recognized and translated text"))
        log_box = QVBoxLayout(log_group)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        log_box.addWidget(self.log)
        cv.addWidget(log_group)
        middle.addWidget(center, 1)

        right = QFrame()
        right.setFixedWidth(304)
        rv = QVBoxLayout(right)
        source = QGroupBox(tr("Capture source"))
        sv = QVBoxLayout(source)
        sv.addWidget(QLabel(tr("Active game window")))
        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.on_window_selected)
        sv.addWidget(self.window_select)
        sv.addWidget(self._button("REFRESH WINDOW LIST", self.refresh_windows))
        self.auto_resize = QCheckBox(tr("Track position and resize automatically"))
        self.auto_resize.setChecked(True)
        self.auto_resize.setEnabled(False)
        sv.addWidget(self.auto_resize)
        rv.addWidget(source)
        overlay_group = QGroupBox(tr("Translate overlay"))
        ov = QVBoxLayout(overlay_group)
        self.overlay_enabled = QCheckBox(tr("Draw translation INSIDE game area"))
        self.overlay_enabled.setChecked(True)
        self.overlay_enabled.toggled.connect(self.update_overlay_anchor)
        ov.addWidget(self.overlay_enabled)
        self.focus_only = QCheckBox(tr("Hide overlay when game is not active"))
        self.focus_only.setChecked(True)
        ov.addWidget(self.focus_only)
        ov.addWidget(QLabel(tr("Chinese OCR -> Vietnamese translation")))
        self.start_btn = self._button("START REAL-TIME TRANSLATION", self.start)
        ov.addWidget(self.start_btn)
        self.stop_btn = self._button("STOP", self.stop)
        self.stop_btn.setEnabled(False)
        ov.addWidget(self.stop_btn)
        rv.addWidget(overlay_group)
        glossary = QGroupBox(tr("Glossary for this game"))
        gl = QVBoxLayout(glossary)
        gl.addWidget(QLabel(tr("One term per line: Chinese = Vietnamese")))
        self.glossary_edit = QPlainTextEdit()
        self.glossary_edit.setPlaceholderText("Example: \u7075\u77f3 = Spirit stone")
        self.glossary_edit.setMaximumHeight(135)
        gl.addWidget(self.glossary_edit)
        gl.addWidget(self._button("SAVE TERMS", self.save_profile))
        rv.addWidget(glossary)
        self.counter = QLabel(tr("Cache: 0 translated phrases"))
        rv.addWidget(self.counter)
        rv.addStretch(1)
        middle.addWidget(right)
        self.status_label = QLabel(tr("Ready. Select a game, capture a preview, then start translation."))
        self.status_label.setObjectName("status")
        v.addWidget(self.status_label)

    def status(self, text):
        self.status_label.setText(text)

    def refresh_windows(self):
        current = self.hwnd
        self.windows = list_game_windows()
        self.window_select.blockSignals(True)
        self.window_select.clear()
        for win in self.windows:
            self.window_select.addItem(f"{win.title[:55]} [HWND: {win.hwnd}]", win.hwnd)
        target = next((i for i, w in enumerate(self.windows) if w.hwnd == current), -1)
        if target < 0:
            target = next((i for i, w in enumerate(self.windows) if w.title == self.profile.window_title), -1)
        if target >= 0:
            self.window_select.setCurrentIndex(target)
        self.window_select.blockSignals(False)
        self.on_window_selected(self.window_select.currentIndex())

    def on_window_selected(self, index):
        self.hwnd = self.window_select.itemData(index) if index >= 0 else None
        if self.hwnd:
            self.profile.window_title = next((w.title for w in self.windows if w.hwnd == self.hwnd), "")

    def refresh_profiles(self):
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        self.profile_list.addItems(sorted(self.profiles))
        matches = self.profile_list.findItems(self.profile.name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.profile_list.setCurrentItem(matches[0])
        self.profile_list.blockSignals(False)

    def choose_profile(self, name):
        if name in self.profiles and not self.running:
            self.profile = self.profiles[name]
            self.load_profile()
            self.refresh_windows()

    def new_profile(self):
        if self.running:
            self.status("Stop translation before changing profiles")
            return
        name = next((w.title for w in self.windows if w.hwnd == self.hwnd), "My game")[:50]
        base = name
        index = 2
        while name in self.profiles:
            name = f"{base} ({index})"
            index += 1
        self.profile = GameProfile(name, base)
        self.load_profile()
        self.status("New profile created. Draw desired OCR regions and click SAVE PROFILE.")

    def load_profile(self):
        self.profile_name.setText(self.profile.name)
        self.preview.set_profile(self.profile)
        self.region_select.setCurrentIndex(0)
        self.select_region()
        self.glossary_edit.setPlainText("\n".join(f"{k} = {v}" for k, v in self.profile.glossary.items()))
        self.counter.setText(f"Cache: {self.cache.count(self.profile.name):,} translated phrases")

    def select_region(self, _=None):
        key = self.region_select.currentData() or "dialogue"
        self.preview.selected_region = key
        self.preview.update()
        self.enable_region.blockSignals(True)
        self.enable_region.setChecked(self.profile.enabled.get(key, False))
        self.enable_region.blockSignals(False)

    def toggle_region(self, checked):
        key = self.region_select.currentData()
        if key:
            self.profile.enabled[key] = bool(checked)

    def on_region_edited(self, key, rect):
        self.profile.regions[key] = rect
        self.status(f"{REGION_LABELS[key]} region updated as percentages. Save the profile.")

    def save_profile(self):
        name = self.profile_name.text().strip()
        if not name:
            self.status("Please provide a profile name")
            return
        old_name = self.profile.name
        if name != old_name and name in self.profiles:
            self.status("A profile with that name already exists")
            return
        self.profile.name = name
        terms = {}
        for line in self.glossary_edit.toPlainText().splitlines():
            if "=" in line:
                left, right = line.split("=", 1)
                if left.strip() and right.strip():
                    terms[left.strip()] = right.strip()
        self.profile.glossary = terms
        if old_name in self.profiles and old_name != name:
            del self.profiles[old_name]
        self.profiles[name] = self.profile
        self.store.save(self.profiles)
        self.refresh_profiles()
        self.counter.setText(f"Cache: {self.cache.count(name):,} translated phrases")
        self.status(f"Profile saved: {name}")

    def capture_preview(self):
        if not self.hwnd:
            self.status("No game window selected")
            return
        try:
            frame, rect = capture_game(self.hwnd)
            self.preview.set_frame(frame)
            self.status(f"Captured {rect[2]} x {rect[3]} game client pixels")
        except Exception as exc:
            self.status(f"Capture failed: {exc}")

    def start(self):
        if not self.hwnd:
            QMessageBox.warning(self, "No game selected", "Select a visible game window first.")
            return
        if game_client_rect(self.hwnd) is None:
            QMessageBox.warning(self, "Game not visible", "Restore the game window and try again.")
            return
        self.save_profile()
        self.running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.scan_timer.start(650)
        self.scan_once()
        self.status("Live translation started. Return focus to the game to see the overlay.")

    def stop(self):
        self.running = False
        self.scan_timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.overlay.hide()
        self.status("Translation stopped")

    def scan_once(self):
        if self.busy or not self.hwnd:
            return
        self.busy = True
        self.task = ScanTask(self.engine, self.hwnd, self.profile)
        self.task.signals.finished.connect(self.scan_done)
        self.task.signals.failed.connect(self.scan_failed)
        self.pool.start(self.task)

    def scan_done(self, result):
        self.busy = False
        self.task = None
        if result["hwnd"] != self.hwnd:
            return
        self.preview.set_frame(result["image"])
        self.overlay.set_results(
            result["blocks"] if self.running else [],
            (result["geometry"][2], result["geometry"][3]),
        )
        logs = []
        for block in result["blocks"]:
            logs.append(f"[{REGION_LABELS[block.region]} / {block.origin}]\n{block.source}\n=> {block.target}")
        if result["errors"]:
            logs.extend(result["errors"])
        self.log.setPlainText("\n\n".join(logs) if logs else "No recognized text in enabled regions.")
        self.counter.setText(f"Cache: {self.cache.count(self.profile.name):,} translated phrases")
        if result["errors"]:
            self.status("OCR/translation problem: " + result["errors"][0][:150])
        else:
            self.status(f"Scanning {result['geometry'][2]} x {result['geometry'][3]} | {len(result['blocks'])} translated regions")
        self.update_overlay_anchor()

    def scan_failed(self, error):
        self.busy = False
        self.task = None
        self.overlay.set_results([])
        self.status("Scan failed: " + error.splitlines()[-1][:180])
        self.log.setPlainText(error)

    def update_overlay_anchor(self):
        if not self.running or not self.overlay_enabled.isChecked() or not self.hwnd:
            self.overlay.hide()
            return
        rect = game_client_rect(self.hwnd)
        if rect is None or (self.focus_only.isChecked() and not is_game_foreground(self.hwnd)):
            self.overlay.hide()
            return
        x, y, w, h = rect
        # Profile rectangles are relative to client size; the overlay is always clipped there.
        if self.overlay.geometry().getRect() != (x, y, w, h):
            self.overlay.setGeometry(x, y, w, h)
        if not self.overlay.isVisible():
            self.overlay.show()
            # Overlay must not steal game focus; Tool + ShowWithoutActivating handles it.
        self.overlay.update()

    def closeEvent(self, event):
        self.stop()
        self.overlay.close()
        event.accept()


def launch_app():
    from .windows import enable_dpi_awareness
    if sys.platform != "win32":
        raise RuntimeError("This desktop capture MVP is designed for Windows 10/11")
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = GameTransWindow()
    window.show()
    return app.exec()
