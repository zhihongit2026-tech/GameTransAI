"""Click-through translation label overlay clipped to the selected game client."""
import sys
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget


from .overlay_layout import translated_rect

class TranslationOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("GameTrans AI Translation Overlay")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.blocks = []
        self.reference_size = (1, 1)
        self.affinity_ok = False

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self.affinity_ok:
            try:
                import ctypes
                from ctypes import wintypes
                fn = ctypes.windll.user32.SetWindowDisplayAffinity
                fn.argtypes = [wintypes.HWND, wintypes.DWORD]
                fn.restype = wintypes.BOOL
                # WDA_EXCLUDEFROMCAPTURE; avoid translating the overlay itself.
                self.affinity_ok = bool(fn(int(self.winId()), 0x00000011))
            except Exception:
                self.affinity_ok = False

    def set_results(self, blocks, reference_size=None):
        self.blocks = list(blocks)
        if reference_size is not None:
            self.reference_size = reference_size
        self.update()

    def paintEvent(self, event):
        if not self.blocks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.rect())
        sx = self.width() / max(1, self.reference_size[0])
        sy = self.height() / max(1, self.reference_size[1])
        for block in self.blocks:
            if not block.target.strip():
                continue
            x, y, w, h = block.box
            x, y, w, h = round(x * sx), round(y * sy), round(w * sx), round(h * sy)
            x, y, w, h = translated_rect((x, y, w, h), (self.width(), self.height()), block.target)
            if w < 16 or h < 14:
                continue
            box = QRectF(x, y, w, h)
            painter.save()
            painter.setClipRect(box)
            painter.setPen(QColor(120, 230, 244, 210))
            painter.setBrush(QColor(5, 18, 28, 233))
            painter.drawRoundedRect(box, 4, 4)
            font = QFont("Microsoft YaHei UI", 10)
            font.setPixelSize(max(12, min(22, int(block.box[3] * sy * 0.85))))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#f5fdff"))
            painter.drawText(QRectF(x + 5, y + 3, w - 10, h - 6),
                             Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, block.target)
            painter.restore()
        painter.end()
