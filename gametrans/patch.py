"""Inpaint OCR text in a small crop using pixels adjacent to the detected box."""
import cv2
import numpy as np


def make_clean_patch(frame: np.ndarray, box, pad=12):
    H, W = frame.shape[:2]
    x, y, w, h = (int(v) for v in box)
    left, top = max(0, x-pad), max(0, y-pad)
    right, bottom = min(W, x+w+pad), min(H, y+h+pad)
    if right <= left or bottom <= top:
        return None
    rgb = np.ascontiguousarray(frame[top:bottom, left:right, :3])
    mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    mask[max(0,y-top):min(mask.shape[0],y+h-top),
         max(0,x-left):min(mask.shape[1],x+w-left)] = 255
    try:
        restored = cv2.inpaint(rgb, mask, 3, cv2.INPAINT_TELEA)
        ox, oy = x-left, y-top
        return np.ascontiguousarray(restored[oy:oy+h, ox:ox+w, :])
    except cv2.error:
        return None
