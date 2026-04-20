from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    pass


class AppConfig:
    def __init__(self, data: dict[str, Any], path: Path):
        self.data = data
        self.path = path
        self.base_dir = path.parent

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path).resolve()
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data, config_path)

    def get(self, dotted: str, default: Any = None) -> Any:
        value: Any = self.data
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def require(self, dotted: str) -> Any:
        value = self.get(dotted)
        if value is None:
            raise ConfigError(f"Missing required config value: {dotted}")
        return value

    def path_value(self, dotted: str, default: str | None = None) -> Path:
        raw = self.get(dotted, default)
        if raw is None:
            raise ConfigError(f"Missing path config value: {dotted}")
        p = Path(str(raw))
        if not p.is_absolute():
            p = self.base_dir / p
        return p.resolve()

    def ensure_log_dir(self) -> Path:
        p = self.path_value("logs.directory", "logs")
        p.mkdir(parents=True, exist_ok=True)
        return p
