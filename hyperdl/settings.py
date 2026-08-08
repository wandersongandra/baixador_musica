"""Gerenciamento de preferencias do usuario persistidas em settings.json."""

import json
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SettingsManager:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def update(self, values: dict[str, Any]):
        with self._lock:
            self._data.update(values)
            try:
                self.path.write_text(
                    json.dumps(self._data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError:
                pass


settings = SettingsManager(PROJECT_ROOT / "settings.json")
