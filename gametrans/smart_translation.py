"""V3: offline-first Chinese -> Vietnamese. No uncontrolled public translation calls.

A local Ollama zh-capable model is optional and is never downloaded silently.
Existing SQLite translations, user TM and built-in UI terms work without a model.
Network translation is strictly opt-in, rate-limited and circuit-broken on HTTP 429.
"""
from __future__ import annotations

import csv
import json
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .models import normalize_source
from .storage import TranslationCache

HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")

# Deterministic, reviewable *UI terms*; no invented story translations.
UI_TERMS = {
    "设置": "Cài đặt", "图像": "Hình ảnh", "基础": "Cơ bản", "声音": "Âm thanh",
    "改键": "Đổi phím", "图像设置": "Cài đặt hình ảnh", "标准": "Tiêu chuẩn",
    "高清": "Chất lượng cao", "超清": "Siêu nét", "至臻": "Cao nhất",
    "自定义": "Tùy chỉnh", "推荐": "Đề xuất", "分辨率": "Độ phân giải",
    "显示模式": "Chế độ hiển thị", "窗口": "Cửa sổ", "全屏": "Toàn màn hình",
    "帧率": "Tốc độ khung hình", "其他玩家特效质量": "Chất lượng hiệu ứng người chơi khác",
    "植被细节": "Chi tiết cây cỏ", "关闭": "Tắt", "低": "Thấp",
    "中": "Trung bình", "高": "Cao", "恢复默认": "Khôi phục mặc định",
    "保存设置": "Lưu cài đặt", "温馨提示": "Lưu ý", "确定": "Xác nhận",
    "开始游戏": "Bắt đầu chơi", "退出游戏": "Thoát game",
    "魂师": "Hồn Sư", "魂环": "Hồn Hoàn", "魂力": "Hồn lực",
    "当前服务器已爆满，请选择其他区域进行登陆": "Máy chủ hiện đã đầy, hãy chọn khu vực khác để đăng nhập",
}


class TranslationUnavailable(Exception):
    """No cached translation, and no working/authorized translation model."""


class RateLimitError(TranslationUnavailable):
    pass


class OnlineRateGate:
    """Limit public requests and suspend them on quota/throttle errors."""
    def __init__(self, interval=2.2, clock=None):
        self.interval = float(interval)
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.next_allowed = 0.0
        self.cooldown_until = 0.0
        self.fails = 0

    def permit(self):
        with self.lock:
            now = self.clock()
            if now < self.cooldown_until:
                raise RateLimitError("Dịch online đang tạm nghỉ do giới hạn yêu cầu")
            if now < self.next_allowed:
                raise RateLimitError("Đang giới hạn tốc độ gọi dịch online")
            self.next_allowed = now + self.interval

    def failure(self, exc):
        msg = str(exc).lower()
        throttle = any(word in msg for word in ("429", "too many", "rate limit", "quota", "blocked"))
        with self.lock:
            self.fails = min(self.fails + 1, 8)
            if throttle:
                self.cooldown_until = self.clock() + min(900, 60 * (2 ** (self.fails - 1)))
            else:
                self.cooldown_until = max(self.cooldown_until, self.clock() + min(60, 3 * self.fails))

    def success(self):
        with self.lock:
            self.fails = 0


class SmartTranslator:
    def __init__(self, cache: TranslationCache, *, local_translate=None,
                 online_translate=None, online_enabled=False,
                 ollama_model="qwen2.5:3b", ollama_url="http://127.0.0.1:11434",
                 clock=None):
        self.cache = cache
        self.local_translate = local_translate
        self.online_translate = online_translate
        self.online_enabled = bool(online_enabled)
        self.model = ollama_model
        self.url = ollama_url.rstrip("/")
        self.gate = OnlineRateGate(clock=clock)
        self._local_blocked_until = 0.0
        self._clock = clock or time.monotonic

    def set_online_enabled(self, value: bool):
        self.online_enabled = bool(value)

    def _local_model(self, text):
        if self.local_translate is not None:
            return self.local_translate(text)
        if self._clock() < self._local_blocked_until:
            raise TranslationUnavailable("Không tìm thấy mô hình offline. Hãy cài Ollama và chạy ollama pull qwen2.5:3b")
        payload = json.dumps({
            "model": self.model, "stream": False,
            "prompt": "Translate the following Chinese game UI text into fluent, concise Vietnamese. "
                      "Preserve names, numbers and item quantities. Output ONLY Vietnamese translation.\n" + text,
            "options": {"temperature": 0.05, "num_predict": 180},
        }).encode("utf-8")
        try:
            request = Request(self.url + "/api/generate", data=payload,
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=15) as response:
                obj = json.loads(response.read().decode("utf-8"))
            value = str(obj.get("response") or "").strip()
            if not value:
                raise ValueError("Mô hình offline trả về rỗng")
            return value
        except (OSError, TimeoutError, ValueError, KeyError) as exc:
            self._local_blocked_until = self._clock() + 15.0
            raise TranslationUnavailable("Mô hình Ollama chưa sẵn sàng: " + str(exc)[:120]) from exc

    def _network_translate(self, text):
        self.gate.permit()
        try:
            if self.online_translate is not None:
                value = self.online_translate(text)
            else:
                from deep_translator import GoogleTranslator
                value = GoogleTranslator(source="zh-CN", target="vi").translate(text)
            if not value:
                raise ValueError("Dịch online trả về rỗng")
        except Exception as exc:
            self.gate.failure(exc)
            raise RateLimitError("Dịch trực tuyến bị giới hạn/lỗi: " + str(exc)[:130]) from exc
        self.gate.success()
        return str(value).strip()

    def translate(self, profile, source, glossary):
        source = normalize_source(source)
        if not source:
            return "", "empty"
        if not HAN.search(source):
            return source, "unchanged"
        if source in glossary:
            return glossary[source], "glossary"
        for p, provider in ((profile, "tm"), ("*", "tm"),
                            (profile, "v3-offline"), (profile, "v3-online"),
                            (profile, "google-zh-vi")):
            old = self.cache.get(p, provider, source)
            if old:
                return old, "cache/" + provider
        if source in UI_TERMS:
            return UI_TERMS[source], "ui-lexicon"
        # An optional offline local model is tried *before* online fallback.
        try:
            value = self._local_model(source)
            provider = "v3-offline"
        except TranslationUnavailable:
            if not self.online_enabled:
                raise
            value = self._network_translate(source)
            provider = "v3-online"
        if not value or not value.strip() or (HAN.search(value) and value == source):
            raise TranslationUnavailable("Chưa có bản dịch tiếng Việt phù hợp")
        self.cache.put(profile, provider, source, value.strip())
        return value.strip(), "offline" if provider == "v3-offline" else "online"


def parse_tm(path: str | Path) -> list[tuple[str, str]]:
    """Read UTF-8-SIG TSV/CSV/TXT source/target pairs; skip unsafe/empty rows."""
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError("Tập tin Translation Memory quá lớn (tối đa 20 MB)")
    content = path.read_text(encoding="utf-8-sig")
    pairs = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        separator = next((s for s in ("\t", "=>", "=", "|") if s in line), None)
        if separator:
            zh, vi = line.split(separator, 1)
        elif path.suffix.lower() == ".csv":
            row = next(csv.reader([line]))
            if len(row) < 2:
                continue
            zh, vi = row[0], row[1]
        else:
            continue
        zh = normalize_source(zh.strip().strip('"'))
        if zh in ("中文", "原文", "源文本", "Source", "source"):
            continue
        vi = vi.strip().strip('"').strip()
        if len(zh) <= 500 and len(vi) <= 1500 and HAN.search(zh) and vi:
            pairs.append((zh, vi))
    return pairs


def import_tm(path: str | Path, cache: TranslationCache, profile: str):
    pairs = parse_tm(path)
    for source, target in pairs:
        cache.put(profile, "tm", source, target)
    return len(pairs)
