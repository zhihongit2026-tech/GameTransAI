"""Serializable, normalized game regions independent of resolution."""
from dataclasses import dataclass, field
from typing import Dict

REGION_LABELS = {
    "dialogue": "Dialogue", "name": "Character name",
    "items": "Items", "subtitle": "Subtitle",
}
DEFAULT_REGIONS = {
    "dialogue": (0.17, 0.75, 0.79, 0.22),
    "name": (0.17, 0.65, 0.28, 0.10),
    "items": (0.70, 0.08, 0.27, 0.35),
    "subtitle": (0.18, 0.88, 0.64, 0.10),
}
def clamp(value, lo, hi):
    return max(lo, min(hi, float(value)))
@dataclass
class NormalizedRect:
    x: float
    y: float
    w: float
    h: float
    def __post_init__(self):
        self.x = clamp(self.x, 0.0, 0.999)
        self.y = clamp(self.y, 0.0, 0.999)
        self.w = clamp(self.w, 0.001, 1.0 - self.x)
        self.h = clamp(self.h, 0.001, 1.0 - self.y)
    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        if width < 1 or height < 1: raise ValueError("Image dimensions must be positive")
        left = min(width - 1, int(round(self.x * width)))
        top = min(height - 1, int(round(self.y * height)))
        right = min(width, max(left + 1, int(round((self.x + self.w) * width))))
        bottom = min(height, max(top + 1, int(round((self.y + self.h) * height))))
        return (left, top, right - left, bottom - top)
    def as_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}
    @classmethod
    def from_dict(cls, data):
        return cls(*(float(data[k]) for k in ("x", "y", "w", "h")))
@dataclass
class GameProfile:
    name: str
    window_title: str
    regions: Dict[str, NormalizedRect] = field(default_factory=lambda: {
        key: NormalizedRect(*values) for key, values in DEFAULT_REGIONS.items()
    })
    enabled: Dict[str, bool] = field(default_factory=lambda: {
        "dialogue": True, "name": False, "items": False, "subtitle": False
    })
    glossary: Dict[str, str] = field(default_factory=dict)
    provider: str = "Google (online)"
    def as_dict(self):
        return {"name":self.name,"window_title":self.window_title,
                "regions":{k:v.as_dict() for k,v in self.regions.items()},
                "enabled":self.enabled,"glossary":self.glossary,"provider":self.provider}
    @classmethod
    def from_dict(cls, data):
        p = cls(name=str(data["name"]), window_title=str(data.get("window_title", "")))
        for key, value in data.get("regions", {}).items():
            if key in DEFAULT_REGIONS:
                try: p.regions[key] = NormalizedRect.from_dict(value)
                except (ValueError, KeyError, TypeError): pass
        p.enabled.update({k: bool(v) for k, v in data.get("enabled", {}).items() if k in DEFAULT_REGIONS})
        p.glossary = {str(k).strip(): str(v).strip() for k,v in data.get("glossary", {}).items() if str(k).strip()}
        return p
def normalize_source(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.strip().splitlines()).strip()
