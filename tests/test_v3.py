"""Deterministic V3 regression tests: no Google/network required."""
from __future__ import annotations
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np
from gametrans.models import GameProfile
from gametrans.storage import TranslationCache
from gametrans.smart_translation import (SmartTranslator, TranslationUnavailable,
                                         RateLimitError, OnlineRateGate, parse_tm,
                                         import_tm)
from gametrans.smart_scanner import SmartScanEngine
from gametrans.patch import make_clean_patch

class FakeOCR:
    def __init__(self):
        self.calls = 0
    def __call__(self, image):
        self.calls += 1
        class Output: pass
        out = Output()
        out.txts = ['设置', '分辨率', '魂师']
        out.scores = np.ones(3,dtype=np.float32)
        out.boxes = np.asarray([[[20,30],[110,30],[110,60],[20,60]],
                                [[100,150],[230,150],[230,180],[100,180]],
                                [[300,240],[360,240],[360,270],[300,270]]],dtype=np.float32)
        return out

class TestSmartTranslator(unittest.TestCase):
    def test_offline_cache_builtin_then_tm(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            calls=[]
            s=SmartTranslator(cache, local_translate=lambda txt: calls.append(txt) or 'Dịch '+txt)
            self.assertEqual(s.translate('Game','设置',{})[0],'Cài đặt')
            cache.put('Game','tm','设置','Thiết lập')
            self.assertEqual(s.translate('Game','设置',{})[0],'Thiết lập')
            self.assertEqual(calls,[])
            a=s.translate('Game','独特技能',{})
            b=s.translate('Game','独特技能',{})
            self.assertEqual(a[0],b[0])
            self.assertEqual(calls,['独特技能'])
            self.assertEqual(b[1],'cache/v3-offline')

    def test_game_menu_labels_from_user_screenshot_work_without_model_or_google(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            called=[]
            def missing(_):
                called.append('offline')
                raise TranslationUnavailable('Ollama not installed')
            def google(_):
                called.append('google')
                raise RuntimeError('429 Too Many Requests')
            translator=SmartTranslator(cache,local_translate=missing,
                                       online_translate=google,online_enabled=True)
            expected={'控制':'Khống chế','毒系':'Hệ Độc',
                      '魔法':'Ma pháp','重新共鸣':'Cộng hưởng lại',
                      '武魂融合':'Dung hợp Võ Hồn'}
            for zh,vi in expected.items():
                self.assertEqual(translator.translate('Douluo',zh,{})[0],vi)
            self.assertEqual(translator.translate('Douluo','·控制·',{})[0],'Khống chế')
            self.assertEqual(called,[])

    def test_fast_glossary_can_override_pending_429(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            translator=SmartTranslator(cache,local_translate=lambda _:(_ for _ in ()).throw(TranslationUnavailable('none')))
            self.assertIsNone(translator.fast_lookup('Douluo','独特法宝',{}))
            cache.put('Douluo','tm','独特法宝','Pháp bảo độc đáo')
            self.assertEqual(translator.fast_lookup('Douluo','独特法宝',{})[0],'Pháp bảo độc đáo')

    def test_no_network_without_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            called=[]
            def offline(_): raise TranslationUnavailable('No Ollama')
            s=SmartTranslator(cache,local_translate=offline,
                              online_translate=lambda t: called.append(t) or 'Online')
            with self.assertRaises(TranslationUnavailable):
                s.translate('Game','未被翻译的技能',{})
            self.assertEqual(called,[])
            s.set_online_enabled(True)
            self.assertEqual(s.translate('Game','未被翻译的技能',{})[0],'Online')
            self.assertEqual(len(called),1)

    def test_http_429_opens_circuit_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            clock=[100.0]
            attempts=[]
            def offline(_): raise TranslationUnavailable('offline unavailable')
            def online(txt):
                attempts.append(txt)
                raise RuntimeError('429 Too Many Requests')
            s=SmartTranslator(cache,local_translate=offline,
                              online_translate=online,online_enabled=True,
                              clock=lambda: clock[0])
            with self.assertRaises(RateLimitError):
                s.translate('A','待翻译文本',{})
            clock[0]+=10
            with self.assertRaises(RateLimitError):
                s.translate('A','另一个待翻译文本',{})
            self.assertEqual(len(attempts),1)

    def test_import_tm_utf8_tsv_and_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'tm.sqlite')
            path=Path(tmp)/'data.tsv'
            path.write_text('中文\tTiếng Việt\n魂帝\tHồn Đế\n无效\t\n',encoding='utf-8-sig')
            self.assertEqual(import_tm(path,cache,'*'),1)
            s=SmartTranslator(cache,local_translate=lambda _: 'Wrong')
            self.assertEqual(s.translate('Douluo','魂帝',{})[0],'Hồn Đế')

class TestSmartScanner(unittest.TestCase):
    def test_async_retains_ocr_boxes_and_does_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=TranslationCache(Path(tmp)/'t.db')
            translator=SmartTranslator(cache,local_translate=lambda t:'VI '+t)
            fake=FakeOCR()
            engine=SmartScanEngine(translator,ocr=fake)
            frame=np.full((360,640,3),160,dtype=np.uint8)
            profile=GameProfile('Game','Game')
            profile.enabled={k:False for k in profile.enabled}
            capture=lambda hwnd:(frame.copy(),(23,44,640,360))
            try:
                first=engine.scan(25,profile,capture)
                for _ in range(40):
                    result=engine.scan(25,profile,capture)
                    if len(result['blocks'])==3: break
                    time.sleep(.01)
                self.assertEqual(len(result['blocks']),3)
                self.assertEqual(fake.calls,1)
                self.assertEqual([b.box[:2] for b in result['blocks']],[(18,28),(98,148),(298,238)])
                self.assertEqual(result['blocks'][0].target,'Cài đặt')
                self.assertEqual(result['blocks'][2].target,'Hồn Sư')
                frame2=np.zeros((720,1280,3),dtype=np.uint8)
                changed=engine.scan(25,profile,lambda _: (frame2,(0,0,1280,720)))
                self.assertEqual(changed['geometry'][2:],(1280,720))
            finally:
                engine.close()

    def test_unknown_model_still_displays_known_screenshot_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            translator=SmartTranslator(TranslationCache(Path(tmp)/'tm.sqlite'),
                                       local_translate=lambda _: (_ for _ in ()).throw(TranslationUnavailable('missing')),
                                       online_enabled=False)
            engine=SmartScanEngine(translator,ocr=FakeOCR())
            frame=np.zeros((360,640,3),dtype=np.uint8)
            profile=GameProfile('Douluo','Douluo')
            try:
                result=engine.scan(1,profile,lambda _: (frame,(0,0,640,360)))
                self.assertEqual([b.target for b in result['blocks']],['Cài đặt','Độ phân giải','Hồn Sư'])
                self.assertEqual(result['pending'],0)
            finally:
                engine.close()

    def test_inpaint_patch_matches_size(self):
        image=np.full((120,240,3),155,dtype=np.uint8)
        image[20:48,38:92]=255
        patch=make_clean_patch(image,(38,20,54,28))
        self.assertIsNotNone(patch)
        self.assertEqual(patch.shape,(28,54,3))
        self.assertLess(float(patch.mean()),200)

if __name__=='__main__':
    unittest.main()
