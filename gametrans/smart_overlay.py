"""Non-invasive native Qt transparent overlay: paint replacement at OCR position.

The app does not inject into or patch game processes. It only draws a
click-through top-level transparent window aligned to a selected HWND client.
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QColor, QPainter, QFont, QFontMetricsF, QPen

from .overlay import TranslationOverlay
from .overlay_layout import translated_rect
from .patch import make_clean_patch




class SmartOverlay(TranslationOverlay):
    def __init__(self):
        super().__init__()
        self._patches = []
        self.setWindowTitle("GameTrans Smart AI V3 Overlay")

    def set_results(self, blocks, reference_size=None, frame=None):
        self.blocks = list(blocks)
        if reference_size is not None:
            self.reference_size = reference_size
        self._patches = []
        if frame is not None:
            for block in self.blocks:
                try:
                    rgb = make_clean_patch(frame, block.box)
                    if rgb is None:
                        self._patches.append(None)
                        continue
                    hh, ww = rgb.shape[:2]
                    self._patches.append(QImage(rgb.data, ww, hh, ww*3,
                                                 QImage.Format.Format_RGB888).copy())
                except Exception:
                    self._patches.append(None)
        self.update()

    def paintEvent(self, event):
        if not self.blocks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setClipRect(self.rect())
        sx = self.width() / max(1, self.reference_size[0])
        sy = self.height() / max(1, self.reference_size[1])
        for i, block in enumerate(self.blocks):
            if not block.target.strip():
                continue
            ox, oy, ow, oh = block.box
            origin = QRectF(ox*sx, oy*sy, ow*sx, oh*sy)
            # Prefer image-inpaint rather than a conspicuous cyan box.
            if i < len(self._patches) and self._patches[i] is not None:
                painter.drawImage(origin, self._patches[i])
            else:
                painter.fillRect(origin, QColor(10, 18, 37, 220))
            x,y,w,h = translated_rect((round(ox*sx), round(oy*sy),
                                       round(ow*sx),round(oh*sy)),
                                      (self.width(),self.height()),block.target)
            if w <= 0 or h <= 0:
                continue
            tx = QRectF(x+2,y+2,max(1,w-4),max(1,h-4))
            painter.save()
            painter.setClipRect(tx)
            font = QFont("Microsoft YaHei UI", 9)
            font.setBold(True)
            font.setPixelSize(max(10,min(23,round(oh*sy*0.83))))
            for size in range(font.pixelSize(),9,-1):
                font.setPixelSize(size)
                metrics = QFontMetricsF(font)
                needed = metrics.boundingRect(tx, int(Qt.TextFlag.TextWordWrap), block.target)
                if needed.height() <= tx.height()+2:
                    break
            painter.setFont(font)
            # A thin shadow improves contrast without a large translation panel.
            painter.setPen(QPen(QColor(0,0,0,210),1.8))
            painter.drawText(tx.translated(1,1), Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, block.target)
            painter.setPen(QColor(252,252,241))
            painter.drawText(tx, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, block.target)
            painter.restore()
        painter.end()
