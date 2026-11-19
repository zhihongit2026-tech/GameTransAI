import tempfile
import unittest
from pathlib import Path

import numpy as np
from gametrans.models import GameProfile
from gametrans.scanner import ScanEngine, dirty_rectangles, image_fingerprint, has_chinese
from gametrans.storage import TranslationCache
from gametrans.translator import Translator


class FakeOutput:
    def __init__(self, texts, boxes=None):
        self.txts = list(texts)
        self.scores = np.ones(len(texts), dtype=np.float32) * .97
        self.boxes = np.array(boxes if boxes is not None else [
            [[5, 8 + 32*i], [65, 8 + 32*i], [65, 30 + 32*i], [5, 30 + 32*i]]
            for i in range(len(texts))], dtype=np.float32)


class FakeOCR:
    def __init__(self, texts=("设置", "分辨率")):
        self.texts = texts
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        return FakeOutput(self.texts)


class TestFullFrameOCR(unittest.TestCase):
    def make_engine(self, folder, ocr):
        invocations = []
        def translate(text):
            invocations.append(text)
            return {"设置": "Cài đặt", "分辨率": "Độ phân giải", "保存设置": "Lưu cài đặt"}.get(text, text)
        engine = ScanEngine(Translator(TranslationCache(Path(folder) / "translations.db"), translate), ocr=ocr)
        return engine, invocations

    def test_no_manual_regions_detects_two_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeOCR()
            engine, invocations = self.make_engine(folder, fake)
            profile = GameProfile("Game", "Game")
            # Legacy MVP left only the dialogue region enabled. V2 must ignore that.
            profile.enabled = {key: False for key in profile.enabled}
            image = np.full((360, 640, 3), 230, dtype=np.uint8)
            capture = lambda hwnd: (image.copy(), (24, 30, 640, 360))
            first = engine.scan(123, profile, capture)
            second = engine.scan(123, profile, capture)
            self.assertEqual([b.source for b in first["blocks"]], ["设置", "分辨率"])
            self.assertEqual([b.target for b in first["blocks"]], ["Cài đặt", "Độ phân giải"])
            self.assertEqual([b.box for b in first["blocks"]], [(3, 6, 64, 26), (3, 38, 64, 26)])
            self.assertEqual(second["blocks"], first["blocks"])
            self.assertEqual(fake.calls, 1)
            self.assertEqual(len(invocations), 2)
            engine.close()

    def test_dirty_tiles_localize_instead_of_scan_everywhere(self):
        a = np.zeros((660, 880, 3), np.uint8)
        b = a.copy()
        b[45:90, 35:115] = 255
        regions = dirty_rectangles(a, b, tile=220, padding=20)
        self.assertEqual(len(regions), 1)
        self.assertLess(regions[0][2], 880)
        self.assertLess(regions[0][3], 660)
        self.assertFalse(dirty_rectangles(b, b))

    def test_resize_invalidates_changed_frame(self):
        a = np.zeros((360, 640, 3), np.uint8)
        b = np.zeros((720, 1280, 3), np.uint8)
        self.assertEqual(dirty_rectangles(a, b), [(0, 0, 1280, 720)])

    def test_fingerprint_and_hanzi(self):
        a = np.zeros((100, 100, 3), dtype=np.uint8)
        b = np.full((100, 100, 3), 255, dtype=np.uint8)
        self.assertNotEqual(image_fingerprint(a), image_fingerprint(b))
        self.assertTrue(has_chinese("保存设置"))
        self.assertFalse(has_chinese("123 Windows"))


if __name__ == '__main__':
    unittest.main()
