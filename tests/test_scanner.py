import tempfile
import unittest
from pathlib import Path
import numpy as np
from gametrans.models import GameProfile
from gametrans.scanner import ScanEngine,image_fingerprint
from gametrans.storage import TranslationCache
from gametrans.translator import Translator

class FakeOutput:
    def __init__(self):
        self.txts=("\u4f60\u597d",)
        self.scores=np.asarray([0.95])
class FakeOCR:
    def __init__(self): self.calls=0
    def __call__(self,_):
        self.calls+=1
        return FakeOutput()

class TestScanner(unittest.TestCase):
    def test_same_frame_does_not_ocr_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            provider_calls=[]
            translator=Translator(TranslationCache(Path(folder)/"cache.db"),
                                  lambda text:provider_calls.append(text) or "Xin chao")
            scanner=ScanEngine(translator)
            scanner.ocr=FakeOCR()
            game=GameProfile("Game A","Demo")
            frame=np.full((360,640,3),255,dtype=np.uint8)
            def capture(_): return frame,(10,20,640,360)
            first=scanner.scan(44,game,capture=capture)
            second=scanner.scan(44,game,capture=capture)
            self.assertEqual(len(first["blocks"]),1)
            self.assertEqual(len(second["blocks"]),1)
            self.assertEqual(scanner.ocr.calls,1)
            self.assertEqual(provider_calls,["\u4f60\u597d"])
    def test_fingerprint_detects_changed_roi(self):
        a=np.zeros((100,100,3),dtype=np.uint8)
        b=np.full((100,100,3),255,dtype=np.uint8)
        self.assertNotEqual(image_fingerprint(a),image_fingerprint(b))
if __name__=="__main__":
    unittest.main()
