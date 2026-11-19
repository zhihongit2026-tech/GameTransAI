"""Network Google Translate provider with persistent SQLite translation memory."""
import re
from .models import normalize_source
from .storage import TranslationCache
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
class TranslationError(Exception): pass
class Translator:
    def __init__(self, cache: TranslationCache, translate_fn=None):
        self.cache = cache
        self._translate_fn = translate_fn
        self._google = None
    def _online_translate(self, text):
        if self._translate_fn is not None: return self._translate_fn(text)
        if self._google is None:
            from deep_translator import GoogleTranslator
            self._google = GoogleTranslator(source="zh-CN",target="vi")
        return self._google.translate(text)
    def translate(self, profile: str, source: str, glossary: dict[str,str]) -> tuple[str,str]:
        source = normalize_source(source)
        if not source: return "", "empty"
        if source in glossary: return glossary[source], "glossary"
        existing = self.cache.get(profile,"google-zh-vi",source)
        if existing is not None: return existing,"cache"
        if not _CJK.search(source): return source,"unchanged"
        try: result=self._online_translate(source[:4000])
        except Exception as exc: raise TranslationError(str(exc)) from exc
        if not result or not result.strip(): raise TranslationError("Provider returned no translation")
        result = result.strip()
        self.cache.put(profile,"google-zh-vi",source,result)
        return result,"online"
