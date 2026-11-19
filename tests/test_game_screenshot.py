"""Regression against the user's 斗罗大陆：诛邪传说 settings screenshot.

Mock-based checks run offline on every build. An actual RapidOCR pass runs on CI
when GAMETRANS_OCR_INTEGRATION=1 (the Windows build installs the OCR engine).
"""
import base64
import os
import unittest
from pathlib import Path

import cv2
import numpy as np

from gametrans.models import GameProfile
from gametrans.scanner import ScanEngine, has_chinese
from gametrans.storage import TranslationCache
from gametrans.translator import Translator

FIXTURE = Path(__file__).parent / "fixtures" / "douluo_settings.jpg.b64"
# Screenshot coordinates from the submitted game settings window, 1358x797.
LABELS = [
    ("设置", (114, 49, 74, 45), "Cài đặt"),
    ("分辨率", (232, 383, 92, 29), "Độ phân giải"),
    ("显示模式", (764, 382, 107, 30), "Chế độ hiển thị"),
    ("保存设置", (1150, 712, 105, 34), "Lưu cài đặt"),
]


def load_image():
    data = base64.b64decode(FIXTURE.read_text(encoding="ascii"))
    im = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        raise RuntimeError("Cannot read the saved real-game screenshot")
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


class ScreenshotMockOCR:
    def __call__(self, frame):
        class Result:
            pass
        output = Result()
        output.txts = [s for s, _, _ in LABELS]
        output.boxes = np.asarray([[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
                                   for _, (x,y,w,h), _ in LABELS], dtype=np.float32)
        output.scores = np.ones(len(LABELS)) * .96
        return output


class ScreenshotTest(unittest.TestCase):
    def test_original_game_image_and_alignment(self):
        image = load_image()
        h, w = image.shape[:2]
        self.assertEqual((w, h), (1358, 797))
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            expected = {source: dest for source, _, dest in LABELS}
            translator = Translator(TranslationCache(Path(folder) / 'cache.db'),
                                    lambda text: expected[text])
            engine = ScanEngine(translator, ocr=ScreenshotMockOCR())
            game = GameProfile('斗罗大陆：诛邪传说', '斗罗大陆：诛邪传说')
            game.enabled = {key: False for key in game.enabled}  # no manual regions
            r = engine.scan(45, game, lambda _: (image, (20,30,w,h)))
            self.assertEqual(len(r['blocks']), 4)
            self.assertEqual({b.source: b.target for b in r['blocks']}, expected)
            for b in r['blocks']:
                self.assertTrue(has_chinese(b.source))
                x,y,bw,bh = b.box
                self.assertGreaterEqual(x,0)
                self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+bw,w)
                self.assertLessEqual(y+bh,h)
            engine.close()

    @unittest.skipUnless(os.getenv('GAMETRANS_OCR_INTEGRATION') == '1',
                         'Set GAMETRANS_OCR_INTEGRATION=1 to run real RapidOCR')
    def test_actual_rapidocr_reads_settings_screenshot(self):
        from rapidocr import RapidOCR
        image = load_image()
        result = RapidOCR()(image)
        texts = list(result.txts) if result.txts is not None else []
        chinese = [t for t in texts if has_chinese(t)]
        self.assertGreaterEqual(len(chinese), 5, f'OCR only found: {texts!r}')
        self.assertTrue(any('设置' in t or '分辨率' in t for t in chinese),
                        f'Missing Chinese menu labels in OCR: {chinese!r}')


if __name__ == '__main__':
    unittest.main()
