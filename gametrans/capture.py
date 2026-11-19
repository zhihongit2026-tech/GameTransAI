"""Prefer DXcam with MSS fallback; both capture only the selected game's client area."""
import sys
import threading
import numpy as np
from .windows import game_client_rect
_state = threading.local()
def capture_game(hwnd: int) -> tuple[np.ndarray, tuple[int,int,int,int]]:
    rect = game_client_rect(hwnd)
    if rect is None: raise RuntimeError("Game window is minimized, closed, or invisible")
    x,y,w,h = rect
    image = None
    if sys.platform == "win32" and x >= 0 and y >= 0:
        try:
            if not hasattr(_state,"dxcam"):
                import dxcam
                _state.dxcam = dxcam.create(output_color="RGB")
            image = _state.dxcam.grab(region=(x,y,x+w,y+h))
            if image is not None and (image.shape[0] != h or image.shape[1] != w): image=None
        except Exception: image=None
    if image is None:
        from mss import mss
        with mss() as monitor:
            frame = np.asarray(monitor.grab({"left":x,"top":y,"width":w,"height":h}))
            image = np.ascontiguousarray(frame[:,:,:3][:,:,::-1])
    return image,rect
