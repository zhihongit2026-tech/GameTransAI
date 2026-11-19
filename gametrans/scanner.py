"""Full-client, position-preserving Chinese OCR with incremental dirty-tile scans.

All OCR/translation work runs in a background worker. Never accesses QWidget.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time

import cv2
import numpy as np

from .capture import capture_game
from .models import GameProfile
from .translator import TranslationError, Translator

HANZI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def has_chinese(text: str) -> bool:
    return bool(HANZI.search(text or ""))


def image_fingerprint(image: np.ndarray) -> bytes:
    """Fast, low-resolution signature for unchanged frames."""
    import hashlib
    h, w = image.shape[:2]
    thumb = cv2.resize(image, (min(256, w), min(144, h)), interpolation=cv2.INTER_AREA)
    return hashlib.blake2b((thumb // 10).tobytes(), digest_size=16).digest()


def intersect(a, b) -> bool:
    x, y, w, h = a
    xx, yy, ww, hh = b
    return x < xx + ww and xx < x + w and y < yy + hh and yy < y + h


def clamp_box(box, width: int, height: int):
    x, y, w, h = [int(round(v)) for v in box]
    left, top = max(0, x), max(0, y)
    right, bottom = min(width, x + w), min(height, y + h)
    if right <= left or bottom <= top:
        return None
    return (left, top, right - left, bottom - top)


def merge_rectangles(rectangles):
    """Union any overlapping/touching dirty areas to avoid duplicated OCR."""
    boxes = list(rectangles)
    changed = True
    while changed:
        changed = False
        merged = []
        while boxes:
            a = boxes.pop()
            i = 0
            while i < len(boxes):
                b = boxes[i]
                # Share boundaries => merge too, for labels straddling tile edges.
                if (a[0] <= b[0] + b[2] and b[0] <= a[0] + a[2]
                        and a[1] <= b[1] + b[3] and b[1] <= a[1] + a[3]):
                    left, top = min(a[0], b[0]), min(a[1], b[1])
                    right, bottom = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    a = (left, top, right - left, bottom - top)
                    boxes.pop(i)
                    changed = True
                    i = 0
                else:
                    i += 1
            merged.append(a)
        boxes = merged
    return boxes


def dirty_rectangles(before: np.ndarray, after: np.ndarray,
                     tile: int = 220, padding: int = 30):
    """Return changed areas or full image when much of the scene changes.

    Detect changes at native scale so a small 18 px Chinese label is not lost
    in downsampling. Decorative motion may cause more OCR but never false cache hits.
    """
    if before is None or before.shape != after.shape:
        h, w = after.shape[:2]
        return [(0, 0, w, h)]
    h, w = after.shape[:2]
    old = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY)
    new = cv2.cvtColor(after, cv2.COLOR_RGB2GRAY)
    rectangles = []
    total, dirty = 0, 0
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            bw, bh = min(tile, w - x), min(tile, h - y)
            total += 1
            d = cv2.absdiff(old[y:y + bh, x:x + bw], new[y:y + bh, x:x + bw])
            # Downsampled hash is insufficient for short game labels.
            if np.count_nonzero(d > 22) / d.size < 0.004 and float(d.mean()) < 1.8:
                continue
            dirty += 1
            left, top = max(0, x - padding), max(0, y - padding)
            right, bottom = min(w, x + bw + padding), min(h, y + bh + padding)
            rectangles.append((left, top, right - left, bottom - top))
    if not rectangles:
        return []
    if dirty / total >= 0.56:
        return [(0, 0, w, h)]
    merged = merge_rectangles(rectangles)
    if len(merged) > 7:
        return [(0, 0, w, h)]
    return merged


@dataclass(frozen=True)
class ScanBlock:
    region: str
    source: str
    target: str
    origin: str
    box: tuple[int, int, int, int]
    confidence: float = 0.0


class ScanEngine:
    """Every OCR detection is its own precisely positioned overlay block."""
    def __init__(self, translator: Translator, ocr=None, max_translators: int = 3):
        self.translator = translator
        self.ocr = ocr
        self.previous_frame = None
        self.prev_blocks: list[ScanBlock] = []
        self.prev_hwnd = None
        self.prev_profile = None
        self.prev_glossary = None
        self.pool = ThreadPoolExecutor(max_workers=max_translators, thread_name_prefix="game-translation")

    def reset(self):
        self.previous_frame = None
        self.prev_blocks = []
        self.prev_hwnd = None
        self.prev_profile = None
        self.prev_glossary = None

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _recognize(self, crop: np.ndarray, offset, full_size):
        if self.ocr is None:
            from rapidocr import RapidOCR
            self.ocr = RapidOCR()
        data = self.ocr(np.ascontiguousarray(crop))
        texts = getattr(data, "txts", None)
        boxes = getattr(data, "boxes", None)
        scores = getattr(data, "scores", None)
        if texts is None or boxes is None:
            return []
        w, h = full_size
        lines = []
        for i, value in enumerate(texts):
            raw = str(value).strip()
            if not has_chinese(raw):
                continue
            score = float(scores[i]) if scores is not None else 1.0
            if score < 0.38:
                continue
            p = np.asarray(boxes[i], dtype=np.float32).reshape(-1, 2)
            if p.size < 4 or not np.isfinite(p).all():
                continue
            x1 = int(np.floor(p[:, 0].min())) + offset[0]
            x2 = int(np.ceil(p[:, 0].max())) + offset[0]
            y1 = int(np.floor(p[:, 1].min())) + offset[1]
            y2 = int(np.ceil(p[:, 1].max())) + offset[1]
            box = clamp_box((x1 - 2, y1 - 2, x2 - x1 + 4, y2 - y1 + 4), w, h)
            if box is not None and box[2] >= 7 and box[3] >= 7:
                lines.append((raw, box, score))
        return lines

    def scan(self, hwnd: int, profile: GameProfile, capture=capture_game):
        started = time.monotonic()
        full, rect = capture(hwnd)
        full = np.ascontiguousarray(full[:, :, :3])
        h, w = full.shape[:2]
        key = (profile.name, tuple(sorted(profile.glossary.items())))
        if hwnd != self.prev_hwnd or key != (self.prev_profile, self.prev_glossary):
            self.reset()
        self.prev_hwnd, self.prev_profile, self.prev_glossary = hwnd, profile.name, key[1]

        roi_list = dirty_rectangles(self.previous_frame, full)
        if not roi_list:
            return {"hwnd": hwnd, "geometry": rect, "image": full,
                    "blocks": list(self.prev_blocks), "errors": [],
                    "ocr_boxes": 0, "elapsed_ms": round((time.monotonic() - started) * 1000)}

        # Retain previous texts only outside all changed regions.
        kept = [b for b in self.prev_blocks if not any(intersect(b.box, r) for r in roi_list)]
        observations = []
        errors = []
        for x, y, rw, rh in roi_list:
            crop = full[y:y + rh, x:x + rw]
            try:
                observations.extend(self._recognize(crop, (x, y), (w, h)))
            except Exception as exc:
                errors.append(f"OCR: {exc}")
                # Failure should not make the whole frame look 'unchanged' forever.
                self.previous_frame = None
                return {"hwnd": hwnd, "geometry": rect, "image": full,
                        "blocks": list(self.prev_blocks), "errors": errors,
                        "ocr_boxes": 0, "elapsed_ms": round((time.monotonic() - started) * 1000)}

        # OCR may duplicate lines in padded neighboring tiles.
        observations.sort(key=lambda item: (item[1][1], item[1][0]))
        unique = []
        for text, box, confidence in observations:
            if any(text == other[0] and intersect(box, other[1]) for other in unique):
                continue
            unique.append((text, box, confidence))

        # SQLite cache and exact glossary matching happen inside Translator.
        # Parallel calls prevent a long menu from taking one network RTT per line.
        # Send identical source text once, even when it appears in multiple UI widgets.
        unique_sources = {text for text, _, _ in unique}
        jobs = {self.pool.submit(self.translator.translate, profile.name, text, profile.glossary): text
                for text in unique_sources}
        translated = {}
        for future in as_completed(jobs):
            source = jobs[future]
            try:
                translated[source] = future.result()
            except Exception as exc:
                errors.append(f"Dịch '{source[:32]}': {exc}")
        blocks = list(kept)
        for text, box, confidence in unique:
            if text in translated:
                target, origin = translated[text]
                if target and target.strip():
                    blocks.append(ScanBlock("auto", text, target, origin, box, confidence))
        blocks.sort(key=lambda b: (b.box[1], b.box[0]))
        self.prev_blocks = blocks
        # Retry failed translations next tick even when pixels have not changed.
        self.previous_frame = None if errors else full.copy()
        return {"hwnd": hwnd, "geometry": rect, "image": full,
                "blocks": blocks, "errors": errors, "ocr_boxes": len(unique),
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
