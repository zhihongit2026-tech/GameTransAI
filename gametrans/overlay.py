"""Click-through, transparent game-client overlay. Does not hook the game process."""
import sys
from PySide6.QtCore import Qt,QRect,QRectF
from PySide6.QtGui import QPainter,QColor,QFont
from PySide6.QtWidgets import QWidget
class TranslationOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("GameTrans AI Translation Overlay")
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        self.blocks=[]
        self.reference_size=(1,1)
        self.affinity_ok=False
    def showEvent(self,event):
        super().showEvent(event)
        if sys.platform=="win32" and not self.affinity_ok:
            try:
                import ctypes
                from ctypes import wintypes
                fn=ctypes.windll.user32.SetWindowDisplayAffinity
                fn.argtypes=[wintypes.HWND,wintypes.DWORD]
                fn.restype=wintypes.BOOL
                self.affinity_ok=bool(fn(int(self.winId()),0x00000011))
            except Exception: self.affinity_ok=False
    def set_results(self,blocks,reference_size=None):
        self.blocks=list(blocks)
        if reference_size is not None: self.reference_size=reference_size
        self.update()
    def paintEvent(self,event):
        if not self.blocks: return
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.rect())
        sx=self.width()/max(1,self.reference_size[0])
        sy=self.height()/max(1,self.reference_size[1])
        for block in self.blocks:
            if not block.target.strip(): continue
            x,y,w,h=block.box
            box=QRect(round(x*sx),round(y*sy),round(w*sx),round(h*sy)).intersected(self.rect())
            if box.width()<24 or box.height()<18: continue
            painter.save()
            painter.setClipRect(box)
            painter.fillRect(box,QColor(4,19,29,226))
            painter.setPen(QColor("#37D7E3"))
            painter.drawRoundedRect(QRectF(box.adjusted(1,1,-2,-2)),7,7)
            f=QFont("Segoe UI",11)
            f.setBold(True)
            f.setPixelSize(max(12,min(24,int(box.height()/max(1.8,len(block.target)/30)))))
            painter.setFont(f)
            painter.setPen(QColor("#F1FAFC"))
            pad=min(12,max(4,box.width()//25))
            painter.drawText(box.adjusted(pad,pad//2,-pad,-pad//2),Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,block.target)
            painter.restore()
        painter.end()
