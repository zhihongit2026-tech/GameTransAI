"""An OCR/translation scan. Must run off the GUI thread."""
from dataclasses import dataclass
import hashlib
import numpy as np
from .capture import capture_game
from .models import GameProfile
from .translator import Translator,TranslationError
def image_fingerprint(image: np.ndarray) -> str:
    import cv2
    h,w=image.shape[:2]
    target=cv2.resize(image,(min(256,w),min(128,h)),interpolation=cv2.INTER_AREA)
    quantized=(target//12).astype(np.uint8)
    return hashlib.blake2s(quantized.tobytes(),digest_size=12).hexdigest()
@dataclass
class ScanBlock:
    region:str
    source:str
    target:str
    origin:str
    box:tuple[int,int,int,int]
class ScanEngine:
    def __init__(self,translator:Translator):
        self.translator=translator
        self.ocr=None
        self.prev_fingerprints={}
        self.prev_blocks={}
        self.prev_hwnd=None
        self.prev_profile=None
        self.prev_signature=None
    def scan(self,hwnd:int,profile:GameProfile,capture=capture_game):
        signature=(profile.name,tuple(sorted(profile.enabled.items())),
                   tuple(sorted(profile.glossary.items())),
                   tuple((key,v.x,v.y,v.w,v.h) for key,v in sorted(profile.regions.items())))
        if self.prev_hwnd != hwnd or self.prev_signature != signature:
            self.prev_fingerprints.clear()
            self.prev_blocks.clear()
            self.prev_hwnd=hwnd
            self.prev_profile=profile.name
            self.prev_signature=signature
        full,rect=capture(hwnd)
        h,w=full.shape[:2]
        blocks=[]
        errors=[]
        for region,area in profile.regions.items():
            if not profile.enabled.get(region,False): continue
            box=area.pixels(w,h)
            x,y,bw,bh=box
            crop=np.ascontiguousarray(full[y:y+bh,x:x+bw])
            fingerprint=image_fingerprint(crop)
            previous=self.prev_blocks.get(region)
            if fingerprint==self.prev_fingerprints.get(region):
                if previous is not None: blocks.append(previous)
                continue
            if self.ocr is None:
                from rapidocr import RapidOCR
                self.ocr=RapidOCR()
            try:
                output=self.ocr(crop)
                texts=[str(t) for t,score in zip(
                    output.txts if output.txts is not None else [],
                    output.scores if output.scores is not None else []
                ) if t and float(score)>=0.40]
                source="\n".join(texts).strip()
                if not source:
                    self.prev_blocks.pop(region,None)
                    self.prev_fingerprints[region]=fingerprint
                    continue
                try: target,origin=self.translator.translate(profile.name,source,profile.glossary)
                except TranslationError as exc:
                    errors.append(f"{region}: translation failed - {exc}")
                    self.prev_fingerprints.pop(region,None)
                    continue
                block=ScanBlock(region,source,target,origin,box)
                self.prev_blocks[region]=block
                self.prev_fingerprints[region]=fingerprint
                blocks.append(block)
            except Exception as exc:
                errors.append(f"{region}: OCR failed - {exc}")
                self.prev_fingerprints.pop(region,None)
        return {"hwnd":hwnd,"geometry":rect,"image":full,"blocks":blocks,"errors":errors}
