"""Chinese -> Vietnamese translation: exact terminology and persistent cache first."""
from __future__ import annotations

import hashlib
import re
import threading

from .models import normalize_source
from .storage import TranslationCache

_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


class TranslationError(Exception):
    pass


class Translator:
    def __init__(self, cache: TranslationCache, translate_fn=None):
        self.cache = cache
        self._translate_fn = translate_fn
        self._local = threading.local()

    def _online_translate(self, text):
        if self._translate_fn is not None:
            return self._translate_fn(text)
        if getattr(self._local, 'google', None) is None:
            from deep_translator import GoogleTranslator
            self._local.google = GoogleTranslator(source='zh-CN', target='vi')
        return self._local.google.translate(text)

    def _uncached(self, source):
        if not _CJK.search(source):
            return source
        try:
            result = self._online_translate(source[:4000])
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        if not result or not str(result).strip():
            raise TranslationError('Dịch vụ không trả về bản dịch.')
        return str(result).strip()

    def translate(self, profile: str, source: str, glossary: dict[str, str]) -> tuple[str, str]:
        source = normalize_source(source)
        if not source:
            return '', 'empty'
        if source in glossary:
            return glossary[source], 'glossary'
        # Glossary changes invalidate only cached phrases affected by that glossary.
        serial = '\n'.join(f'{k}={v}' for k, v in sorted(glossary.items()))
        suffix = ':' + hashlib.blake2s(serial.encode('utf-8'), digest_size=6).hexdigest() if serial else ''
        provider = 'google-zh-vi' + suffix
        previous = self.cache.get(profile, provider, source)
        if previous is not None:
            return previous, 'cache'
        if not _CJK.search(source):
            return source, 'unchanged'

        # Longest-match glossary replacement inside a sentence. Split instead
        # of relying on a translation API to preserve artificial placeholders.
        terms = [k for k in glossary if k and k in source]
        if terms:
            expression = re.compile('(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + ')')
            parts = expression.split(source)
            translated = []
            for part in parts:
                if not part:
                    continue
                if part in glossary:
                    translated.append(glossary[part])
                else:
                    translated.append(self._uncached(part))
            result = ' '.join(v for v in translated if v).strip()
            origin = 'glossary+online'
        else:
            result = self._uncached(source)
            origin = 'online'
        self.cache.put(profile, provider, source, result)
        return result, origin
