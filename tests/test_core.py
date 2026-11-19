import tempfile
import unittest
from pathlib import Path
from gametrans.models import GameProfile,NormalizedRect,normalize_source
from gametrans.storage import ProfileStore,TranslationCache
from gametrans.translator import Translator,TranslationError

class TestRegion(unittest.TestCase):
    def test_resize_percentages(self):
        region=NormalizedRect(0.2,0.75,0.5,0.2)
        self.assertEqual(region.pixels(1000,500),(200,375,500,100))
        self.assertEqual(region.pixels(2000,1000),(400,750,1000,200))
    def test_clip_invalid_profile_region(self):
        region=NormalizedRect(0.9,0.8,0.8,0.7)
        x,y,w,h=region.pixels(1280,720)
        self.assertLessEqual(x+w,1280)
        self.assertLessEqual(y+h,720)
    def test_normalize_text(self):
        self.assertEqual(normalize_source("  \u4f60  \u597d \n \u4e16\u754c  "),"\u4f60 \u597d\n\u4e16\u754c")

class TestPersistence(unittest.TestCase):
    def test_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            p=GameProfile("Game A","My Game")
            p.regions["dialogue"]=NormalizedRect(.1,.2,.3,.4)
            p.glossary={"\u7075\u77f3":"Linh thach"}
            store=ProfileStore(Path(folder)/"profiles.json")
            store.save({p.name:p})
            loaded=store.load()[p.name]
            self.assertEqual(loaded.regions["dialogue"].as_dict(),p.regions["dialogue"].as_dict())
            self.assertEqual(loaded.glossary["\u7075\u77f3"],"Linh thach")
    def test_sqlite_hit_and_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=TranslationCache(Path(folder)/"cache.sqlite3")
            self.assertIsNone(cache.get("Game A","google-zh-vi","\u4f60\u597d"))
            cache.put("Game A","google-zh-vi","\u4f60\u597d","Xin chao")
            self.assertEqual(cache.get("Game A","google-zh-vi","\u4f60\u597d"),"Xin chao")
            cache.put("Game A","google-zh-vi","\u4f60\u597d","Chao ban")
            self.assertEqual(cache.count("Game A"),1)
            self.assertEqual(cache.get("Game A","google-zh-vi","\u4f60\u597d"),"Chao ban")

class TestTranslator(unittest.TestCase):
    def test_cache_avoids_network(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def fake(text):
                calls.append(text)
                return "Xin chao"
            translator=Translator(TranslationCache(Path(folder)/"cache.db"),fake)
            for _ in range(3):
                val,_=translator.translate("Game A","\u4f60\u597d",{})
                self.assertEqual(val,"Xin chao")
            self.assertEqual(len(calls),1)
    def test_exact_glossary_skips_network(self):
        with tempfile.TemporaryDirectory() as folder:
            translator=Translator(TranslationCache(Path(folder)/"cache.db"),lambda t:"WRONG")
            value,origin=translator.translate("Game A","\u7075\u77f3",{"\u7075\u77f3":"Linh thach"})
            self.assertEqual((value,origin),("Linh thach","glossary"))
    def test_network_error_not_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=TranslationCache(Path(folder)/"cache.db")
            def fail(_): raise TimeoutError("test timeout")
            with self.assertRaises(TranslationError):
                Translator(cache,fail).translate("Game A","\u4f60\u597d",{})
            self.assertEqual(cache.count(),0)
if __name__=="__main__":
    unittest.main()
