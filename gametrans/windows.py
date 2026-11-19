"""Windows-only capture target enumeration; coordinates are the GAME CLIENT AREA."""
import sys
from dataclasses import dataclass
if sys.platform=="win32":
    import ctypes
    from ctypes import wintypes
    user32=ctypes.windll.user32
    WNDENUMPROC=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    class POINT(ctypes.Structure):
        _fields_=[("x",wintypes.LONG),("y",wintypes.LONG)]
    class RECT(ctypes.Structure):
        _fields_=[("left",wintypes.LONG),("top",wintypes.LONG),("right",wintypes.LONG),("bottom",wintypes.LONG)]
    user32.EnumWindows.argtypes=[WNDENUMPROC,wintypes.LPARAM]
    user32.EnumWindows.restype=wintypes.BOOL
    user32.IsWindow.argtypes=[wintypes.HWND]
    user32.IsWindow.restype=wintypes.BOOL
    user32.IsWindowVisible.argtypes=[wintypes.HWND]
    user32.IsWindowVisible.restype=wintypes.BOOL
    user32.IsIconic.argtypes=[wintypes.HWND]
    user32.IsIconic.restype=wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user32.GetWindowTextLengthW.restype=ctypes.c_int
    user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user32.GetWindowTextW.restype=ctypes.c_int
    user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(RECT)]
    user32.GetClientRect.restype=wintypes.BOOL
    user32.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(POINT)]
    user32.ClientToScreen.restype=wintypes.BOOL
    user32.GetForegroundWindow.restype=wintypes.HWND

def enable_dpi_awareness():
    if sys.platform!="win32": return
    import ctypes
    try: user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception: pass

@dataclass(frozen=True)
class WindowInfo:
    hwnd:int
    title:str

def list_game_windows()->list[WindowInfo]:
    if sys.platform!="win32": return []
    windows=[]
    @WNDENUMPROC
    def callback(hwnd,_):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd): return True
        count=user32.GetWindowTextLengthW(hwnd)
        if count<3: return True
        import ctypes
        buf=ctypes.create_unicode_buffer(count+1)
        user32.GetWindowTextW(hwnd,buf,len(buf))
        title=buf.value.strip()
        if title and not title.lower().startswith("gametrans ai"):
            windows.append(WindowInfo(int(hwnd),title))
        return True
    user32.EnumWindows(callback,0)
    return windows

def game_client_rect(hwnd:int):
    if sys.platform!="win32": return None
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd): return None
    rect=RECT()
    origin=POINT(0,0)
    if not user32.GetClientRect(hwnd,__import__("ctypes").byref(rect)): return None
    if not user32.ClientToScreen(hwnd,__import__("ctypes").byref(origin)): return None
    w,h=rect.right-rect.left,rect.bottom-rect.top
    if w<=5 or h<=5: return None
    return (origin.x,origin.y,w,h)
def is_game_foreground(hwnd):
    return sys.platform=="win32" and int(user32.GetForegroundWindow())==int(hwnd)
