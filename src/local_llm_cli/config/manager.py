"""Configuration manager built on Pydantic settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_YAML = False

from .schema import AppConfig


class ConfigManager:
    """Load/save helper around the application configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self.get_default_config_path()
        self._config: Optional[AppConfig] = None

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[3]

    @classmethod
    def get_default_config_path(cls) -> Path:
        config_dir = cls.project_root() / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        if HAS_YAML:
            return config_dir / "config.yaml"
        return config_dir / "config.json"

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            config = AppConfig.default()
            self.save(config)
            self._config = config
            return config

        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                if self.config_path.suffix in {".yaml", ".yml"} and HAS_YAML:
                    raw = yaml.safe_load(handle) or {}
                else:
                    raw = json.load(handle)
        except Exception as exc:  # pragma: no cover - fallback path
            print(f"Warning: Failed to load config from {self.config_path}: {exc}")
            print("Falling back to default configuration")
            config = AppConfig.default()
            self._config = config
            return config

        config = AppConfig.from_dict(raw or {})
        self._config = config
        return config

    def save(self, config: AppConfig) -> bool:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = config.to_dict()
            with open(self.config_path, "w", encoding="utf-8") as handle:
                if self.config_path.suffix in {".yaml", ".yml"} and HAS_YAML:
                    yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
                else:
                    json.dump(data, handle, indent=2)
            self._config = config
            return True
        except Exception as exc:  # pragma: no cover - IO failure
            print(f"Error saving config to {self.config_path}: {exc}")
            return False

    def get(self) -> AppConfig:
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> AppConfig:
        self._config = None
        return self.load()


_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[Path] = None) -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager


def get_config(config_path: Optional[Path] = None) -> AppConfig:
    return get_config_manager(config_path).get()


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    return get_config_manager(config_path).load()


def save_config(config: AppConfig, config_path: Optional[Path] = None) -> bool:
    manager = get_config_manager(config_path)
    return manager.save(config)
