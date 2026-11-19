"""V3 incremental full-window OCR; translations never block the recognition thread."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .capture import capture_game
from .models import GameProfile
from .scanner import ScanEngine, ScanBlock, dirty_rectangles, intersect
from .smart_translation import TranslationUnavailable


@dataclass(frozen=True)
class Observation:
    source: str
    box: tuple[int, int, int, int]
    confidence: float


class SmartScanEngine(ScanEngine):
    """Return OCR detections promptly; resolved text appears on following frames.

    OCR scans only changed tiles. UI translates asynchronously via a bounded queue;
    jobs from a previous game/profile are never overlaid onto the new one.
    """
    def __init__(self, translator, ocr=None, max_pending=48):
        super().__init__(translator, ocr=ocr, max_translators=1)
        self.translate_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smart-vi")
        self.max_pending = max_pending
        self.observations = []
        self.pending = {}
        self.resolved = {}
        self.error_until = {}
        self.last_warning = ""

    def reset(self):
        super().reset()
        self.observations = []
        self.pending = {}
        self.resolved = {}
        self.error_until = {}
        self.last_warning = ""

    def close(self):
        self.translate_pool.shutdown(wait=False, cancel_futures=True)
        super().close()

    def _poll(self):
        now = time.monotonic()
        for text, future in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[text]
            try:
                target, origin = future.result()
                if target:
                    self.resolved[text] = (target, origin)
            except TranslationUnavailable as exc:
                self.error_until[text] = now + 20
                self.last_warning = str(exc)[:120]
            except Exception as exc:
                self.error_until[text] = now + 30
                self.last_warning = str(exc)[:120]

    def scan(self, hwnd: int, profile: GameProfile, capture=capture_game):
        start = time.monotonic()
        frame, rect = capture(hwnd)
        frame = np.ascontiguousarray(frame[:, :, :3])
        h, w = frame.shape[:2]
        key = (profile.name, tuple(sorted(profile.glossary.items())),
               getattr(self.translator, "online_enabled", False))
        if hwnd != self.prev_hwnd or key != self.prev_profile:
            self.reset()
        self.prev_hwnd, self.prev_profile, self.prev_glossary = hwnd, key, key[1]
        self._poll()
        regions = dirty_rectangles(self.previous_frame, frame)
        errors = []
        if regions:
            kept = [b for b in self.observations
                    if not any(intersect(b.box, r) for r in regions)]
            fresh = []
            for x, y, rw, rh in regions:
                try:
                    for source, box, score in self._recognize(frame[y:y+rh, x:x+rw],
                                                               (x, y), (w, h)):
                        if not any(source == a.source and intersect(box, a.box) for a in fresh):
                            fresh.append(Observation(source, box, score))
                except Exception as exc:
                    errors.append("Lỗi OCR: " + str(exc)[:160])
            if errors:
                self.previous_frame = None
            else:
                self.previous_frame = frame.copy()
                self.observations = sorted(kept + fresh, key=lambda a: (a.box[1], a.box[0]))
        # Offline terms/TM return almost instantly; unseen sentences queue in the background.
        # Resolved results are never allowed to survive a profile/glossary switch.
        now = time.monotonic()
        for source in {o.source for o in self.observations}:
            if source in self.resolved:
                continue
            # New TM/glossary terms can resolve immediately even when an older
            # online attempt failed or the provider is currently rate-limited.
            fast = getattr(self.translator, "fast_lookup", None)
            result = fast(profile.name, source, profile.glossary) if callable(fast) else None
            if result:
                self.resolved[source] = result
                self.error_until.pop(source, None)
                self.last_warning = ""
                continue
            if source in self.pending or now < self.error_until.get(source, 0):
                continue
            if len(self.pending) >= self.max_pending:
                break
            self.pending[source] = self.translate_pool.submit(
                self.translator.translate, profile.name, source, dict(profile.glossary))
        self._poll()
        translated = [ScanBlock("auto", o.source, self.resolved[o.source][0],
                                self.resolved[o.source][1], o.box, o.confidence)
                      for o in self.observations if o.source in self.resolved]
        return {"hwnd": hwnd, "geometry": rect, "image": frame,
                "blocks": translated, "errors": errors, "pending": len(self.pending),
                "detected": len(self.observations), "warning": self.last_warning,
                "elapsed_ms": round((time.monotonic() - start)*1000)}
