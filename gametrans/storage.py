"""Persist profiles and translated phrases locally, never in the repository."""
import json
from contextlib import closing
import os
import sqlite3
from pathlib import Path
from .models import GameProfile, normalize_source

def data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    folder = root / "GameTransAI"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

class ProfileStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "profiles.json"
    def load(self):
        if not self.path.is_file(): return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return {p.name: p for raw in payload.get("profiles", []) if (p := GameProfile.from_dict(raw))}
        except (ValueError, TypeError, KeyError, OSError): return {}
    def save(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"profiles": [p.as_dict() for p in profiles.values()]},ensure_ascii=False,indent=2),encoding="utf-8")
        temp.replace(self.path)

class TranslationCache:
    def __init__(self, path=None):
        self.path = str(Path(path) if path else data_dir() / "translations.sqlite3")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS translations (
                profile TEXT NOT NULL,
                provider TEXT NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (profile, provider, source)
            )""")
            db.commit()
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5.0)
        db.execute("PRAGMA busy_timeout = 5000")
        return db
    def get(self, profile, provider, source):
        source = normalize_source(source)
        with closing(self._connect()) as db:
            hit = db.execute("SELECT target FROM translations WHERE profile=? AND provider=? AND source=?",
                             (profile,provider,source)).fetchone()
        return hit[0] if hit else None
    def put(self, profile, provider, source, target):
        source = normalize_source(source)
        if not source or not target: return
        with closing(self._connect()) as db:
            db.execute("""INSERT INTO translations (profile, provider, source, target)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile, provider, source)
                DO UPDATE SET target=excluded.target, updated_at=CURRENT_TIMESTAMP""",
                (profile,provider,source,target))
            db.commit()
    def count(self, profile=None):
        with closing(self._connect()) as db:
            if profile: return db.execute("SELECT COUNT(*) FROM translations WHERE profile=?", (profile,)).fetchone()[0]
            return db.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
