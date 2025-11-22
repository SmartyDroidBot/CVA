"""Configuration manager built on Pydantic settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_YAML = False

from .schema import AppConfig


class ConfigManager:
    """Load/save helper around the application configuration."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        agents_path: Optional[Path] = None,
        mcp_path: Optional[Path] = None,
    ):
        self.config_path = config_path or self.get_default_config_path()
        base_dir = self.config_path.parent
        suffix = ".yaml" if HAS_YAML else ".json"
        default_agents = base_dir / f"agents{suffix}"
        default_mcp = base_dir / f"mcp_servers{suffix}"
        self.agents_path = agents_path or default_agents
        self.mcp_path = mcp_path or default_mcp
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
            raw = self._read_file(self.config_path)
        except Exception as exc:  # pragma: no cover - fallback path
            print(f"Warning: Failed to load config from {self.config_path}: {exc}")
            print("Falling back to default configuration")
            config = AppConfig.default()
            self._config = config
            return config

        if "agents" not in raw:
            raw["agents"] = self._safe_read_section(self.agents_path)
        if "mcp_servers" not in raw:
            raw["mcp_servers"] = self._safe_read_section(self.mcp_path)

        config = AppConfig.from_dict(raw or {})
        self._config = config
        return config

    def save(self, config: AppConfig) -> bool:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = config.to_dict()
            agents = data.pop("agents", {})
            mcp_servers = data.pop("mcp_servers", {})
            self._write_file(self.config_path, data)
            self._write_file(self.agents_path, agents)
            self._write_file(self.mcp_path, mcp_servers)
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

    def _read_file(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            if path.suffix in {".yaml", ".yml"} and HAS_YAML:
                return yaml.safe_load(handle) or {}
            return json.load(handle)

    def _safe_read_section(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return self._read_file(path)
        except Exception:  # pragma: no cover - section parsing fallback
            return {}

    def _write_file(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            if path.suffix in {".yaml", ".yml"} and HAS_YAML:
                yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, handle, indent=2)


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
