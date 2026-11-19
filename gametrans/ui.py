"""GameTrans Smart AI V3 compact launcher; live work happens on top of game."""
from __future__ import annotations

import copy
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from .models import GameProfile
from .smart_overlay import SmartOverlay
from .smart_scanner import SmartScanEngine
from .smart_translation import SmartTranslator, import_tm
from .storage import ProfileStore, TranslationCache
from .windows import (enable_dpi_awareness, game_client_rect, is_game_foreground,
                      list_game_windows)

STYLE = """
QMainWindow, QWidget { background: #101d30; color: #f0f5fb; font: 10pt 'Segoe UI'; }
QLabel#title { color: #59eff0; font: bold 17pt 'Segoe UI'; }
QLabel#muted { color: #a6bfd4; }
QLabel#status { color: #a6f0be; }
QComboBox { background: #1a2c43; color: white; border: 1px solid #4b6d89;
  border-radius: 8px; padding: 10px; }
QPushButton { background: #126e8b; border: 1px solid #4ca7cc; border-radius: 8px;
  padding: 10px; font-weight: 600; }
QPushButton:hover { background: #148db1; }
QPushButton#start { background: #009b9e; font-size: 12pt; padding: 14px; }
QCheckBox { spacing: 8px; }
"""


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
            self.signals.finished.emit(self.engine.scan(self.hwnd,self.profile),self.epoch)
        except Exception:
            self.signals.failed.emit(traceback.format_exc(limit=4),self.epoch)


def tray_icon():
    pix = QPixmap(48,48)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#039eac"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2,2,44,44,10,10)
    p.setPen(QColor("white"))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(24)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    p.end()
    return QIcon(pix)


class SmartGameWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameTrans Smart AI V3 - Việt hóa trực tiếp trong game")
        self.resize(610,395)
        self.setMinimumWidth(520)
        self.cache=TranslationCache()
        self.profiles_store=ProfileStore()
        self.profiles=self.profiles_store.load()
        self.profile=GameProfile("Game", "")
        self.translator=SmartTranslator(self.cache)
        self.engine=SmartScanEngine(self.translator)
        self.overlay=SmartOverlay()
        self.windows=[]
        self.hwnd=None
        self.running=False
        self.busy=False
        self.task=None
        self.epoch=0
        self.last_size=None
        self.pool=QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._quit_now=False
        self._build_ui()
        self._configure_tray()
        self.refresh_windows()
        self.scan_timer=QTimer(self)
        self.scan_timer.timeout.connect(self.scan_once)
        self.anchor_timer=QTimer(self)
        self.anchor_timer.timeout.connect(self.update_overlay_anchor)
        self.anchor_timer.start(100)

    def _build_ui(self):
        outer=QVBoxLayout()
        outer.setContentsMargins(22,20,22,16)
        outer.setSpacing(10)
        title=QLabel("🎮 GameTrans Smart AI V3")
        title.setObjectName("title")
        outer.addWidget(title)
        note=QLabel("Chọn game → dịch ngay trên game → ứng dụng chạy ẩn ở khay hệ thống")
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addWidget(QLabel("Cửa sổ game đang mở"))
        row=QHBoxLayout()
        self.game_select=QComboBox()
        self.game_select.activated.connect(self._game_activated)
        row.addWidget(self.game_select,1)
        refresh=QPushButton("↻ Làm mới")
        refresh.clicked.connect(self.refresh_windows)
        row.addWidget(refresh)
        outer.addLayout(row)
        self.status_label=QLabel("Sẵn sàng. Chọn game để bắt đầu dịch.")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.offline_info=QLabel("Ưu tiên: Từ điển + Translation Memory + mô hình Ollama trên máy")
        self.offline_info.setObjectName("muted")
        self.offline_info.setWordWrap(True)
        outer.addWidget(self.offline_info)
        self.online_check=QCheckBox("Cho phép dịch online khi thiếu mô hình/bản dịch offline")
        self.online_check.setChecked(False)
        self.online_check.toggled.connect(self._provider_changed)
        outer.addWidget(self.online_check)
        self.focus_only=QCheckBox("Chỉ hiện tiếng Việt khi đang chơi game")
        self.focus_only.setChecked(True)
        self.focus_only.toggled.connect(self.update_overlay_anchor)
        outer.addWidget(self.focus_only)
        actions=QHBoxLayout()
        self.tm_button=QPushButton("Nhập Translation Memory")
        self.tm_button.clicked.connect(self.import_memory)
        actions.addWidget(self.tm_button)
        self.model_help=QPushButton("Thiết lập dịch offline")
        self.model_help.clicked.connect(self.show_model_help)
        actions.addWidget(self.model_help)
        outer.addLayout(actions)
        self.start_button=QPushButton("▶ CHỌN GAME VÀ DỊCH")
        self.start_button.setObjectName("start")
        self.start_button.clicked.connect(self.start)
        outer.addWidget(self.start_button)
        self.stop_button=QPushButton("■ Dừng dịch")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        outer.addWidget(self.stop_button)
        root=QWidget()
        root.setLayout(outer)
        self.setCentralWidget(root)

    def _configure_tray(self):
        self.tray=QSystemTrayIcon(tray_icon(),self)
        menu=QMenu()
        menu.addAction("Mở GameTrans Smart AI",self.restore_window)
        self.pause_action=menu.addAction("Tạm dừng dịch",self.toggle_pause)
        menu.addSeparator()
        menu.addAction("Thoát hẳn",self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.setWindowIcon(self.tray.icon())

    def _tray_activated(self, reason):
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if self.running and self.tray.isVisible():
            self.hide()
        elif self.running:
            self.showMinimized()

    def status(self, message):
        self.status_label.setText(message)
        self.tray.setToolTip("GameTrans Smart AI V3\n"+message[:110])

    def refresh_windows(self):
        old=self.hwnd
        self.windows=list_game_windows()
        self.game_select.blockSignals(True)
        self.game_select.clear()
        self.game_select.addItem("-- Chọn game đang chạy --",None)
        for win in self.windows:
            self.game_select.addItem(win.title[:75],win.hwnd)
        index=next((i for i in range(1,self.game_select.count())
                    if self.game_select.itemData(i)==old),0)
        self.game_select.setCurrentIndex(index)
        self.game_select.blockSignals(False)
        self.start_button.setEnabled(bool(self.game_select.currentData()))

    def _game_activated(self,index):
        hwnd=self.game_select.itemData(index)
        if not hwnd:
            return
        if self.running:
            self.stop()
        self.hwnd=int(hwnd)
        name=next((w.title for w in self.windows if w.hwnd==hwnd),"Game")
        self.profile=self.profiles.get(name,GameProfile(name,name))
        self.online_check.blockSignals(True)
        self.online_check.setChecked(self.profile.provider=="offline+online")
        self.online_check.blockSignals(False)
        self.translator.set_online_enabled(self.online_check.isChecked())
        self.start()

    def _provider_changed(self,enabled):
        self.translator.set_online_enabled(enabled)
        self.profile.provider="offline+online" if enabled else "offline"
        if self.hwnd:
            self.profiles[self.profile.name]=self.profile
            self.profiles_store.save(self.profiles)
            self.engine.reset() if not self.busy else None

    def show_model_help(self):
        QMessageBox.information(self,"Dịch offline", "Để dịch mọi câu mới ngay trên máy:\n\n"
            "1. Cài Ollama cho Windows từ https://ollama.com\n"
            "2. Mở Terminal và chạy: ollama pull qwen2.5:3b\n"
            "3. Đảm bảo Ollama chạy, sau đó chọn game.\n\n"
            "Không có Ollama vẫn dịch được các cụm đã lưu trong Translation Memory "
            "và từ điển giao diện. Không tự động gửi chữ ra Internet nếu chưa bật tùy chọn online.")

    def import_memory(self):
        filename,_=QFileDialog.getOpenFileName(self,"Nhập Translation Memory", "",
                                                  "Translation Memory (*.txt *.tsv *.csv)")
        if not filename:
            return
        try:
            count=import_tm(filename,self.cache,self.profile.name if self.hwnd else "*")
            if not self.busy:
                self.engine.reset()
            self.status(f"Đã thêm {count} cặp câu dịch vào bộ nhớ. Lần quét tiếp sẽ dùng chúng.")
        except Exception as exc:
            QMessageBox.warning(self,"Không nhập được Translation Memory",str(exc))

    def start(self):
        if not self.hwnd:
            hwnd=self.game_select.currentData()
            if hwnd is not None:
                self.hwnd=int(hwnd)
                name=next((w.title for w in self.windows if w.hwnd==hwnd),"Game")
                self.profile=self.profiles.get(name,GameProfile(name,name))
        if not self.hwnd or game_client_rect(self.hwnd) is None:
            self.status("Game đã đóng, thu nhỏ hoặc chưa chọn. Hãy mở game rồi chọn lại.")
            return
        self.profiles[self.profile.name]=self.profile
        self.profiles_store.save(self.profiles)
        self.translator.set_online_enabled(self.online_check.isChecked())
        self.epoch+=1
        if not self.busy:
            self.engine.reset()
        self.running=True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.pause_action.setText("Tạm dừng dịch")
        self.scan_timer.start(500)
        self.scan_once()
        self.status("Đang nhận chữ và Việt hóa trực tiếp trong game. Đổi sang cửa sổ game để xem.")
        QTimer.singleShot(200,self.hide_to_tray)

    def stop(self):
        self.epoch+=1
        self.running=False
        self.scan_timer.stop()
        self.overlay.hide()
        self.overlay.set_results([])
        self.start_button.setEnabled(bool(self.hwnd))
        self.stop_button.setEnabled(False)
        self.pause_action.setText("Tiếp tục dịch")
        self.status("Đã tạm dừng. Nhấn Tiếp tục dịch ở biểu tượng khay hệ thống.")

    def toggle_pause(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def scan_once(self):
        if not self.running or self.busy or not self.hwnd:
            return
        if game_client_rect(self.hwnd) is None:
            self.overlay.hide()
            return
        self.busy=True
        self.task=ScanTask(self.engine,self.hwnd,self.profile,self.epoch)
        self.task.signals.finished.connect(self.scan_done)
        self.task.signals.failed.connect(self.scan_failed)
        self.pool.start(self.task)

    def scan_done(self,result,epoch):
        self.busy=False
        self.task=None
        if not self.running or epoch!=self.epoch or result["hwnd"]!=self.hwnd:
            return
        rect=game_client_rect(self.hwnd)
        if rect is None:
            self.overlay.hide()
            return
        if rect[2:]!=result["geometry"][2:]:
            self.overlay.set_results([])
            self.scan_once()
            return
        self.overlay.set_results(result["blocks"],rect[2:],result["image"])
        if result["errors"]:
            self.status(result["errors"][0])
        elif result["warning"] and not result["blocks"]:
            self.status(result["warning"] + " — dùng TM hoặc bật mô hình offline.")
        else:
            self.status(f"Đã phát hiện {result['detected']} cụm Trung, "
                        f"đang hiển thị {len(result['blocks'])} bản dịch; "
                        f"đang xử lý {result['pending']} cụm.")
        self.update_overlay_anchor()

    def scan_failed(self,message,epoch):
        self.busy=False
        self.task=None
        if epoch!=self.epoch:
            return
        self.overlay.hide()
        self.status("Lỗi chụp/OCR: " + message.splitlines()[-1][:145])

    def update_overlay_anchor(self):
        if not self.running or not self.hwnd:
            self.overlay.hide()
            return
        rect=game_client_rect(self.hwnd)
        if rect is None or (self.focus_only.isChecked() and not is_game_foreground(self.hwnd)):
            self.overlay.hide()
            return
        if self.overlay.geometry().getRect()!=rect:
            self.overlay.setGeometry(*rect)
            if self.last_size and rect[2:]!=self.last_size:
                self.overlay.set_results([])
            self.last_size=rect[2:]
        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.update()

    def closeEvent(self,event):
        if not self._quit_now and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        self._cleanup()
        event.accept()

    def _cleanup(self):
        self.running=False
        self.scan_timer.stop()
        self.overlay.hide()
        self.overlay.close()
        self.engine.close()
        self.tray.hide()

    def quit_app(self):
        self._quit_now=True
        self.close()
        QApplication.instance().quit()


def launch_app():
    if sys.platform!="win32":
        raise RuntimeError("GameTrans Smart AI V3 requires Windows 10/11")
    enable_dpi_awareness()
    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window=SmartGameWindow()
    window.show()
    return app.exec()
