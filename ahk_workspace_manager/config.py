from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_DATA_DIR_NAME = "AHKQuickLaunchManager"
CONFIG_FILENAME = "workspace_manager.json"
LEGACY_CONFIG_FILE = Path(CONFIG_FILENAME)
LEGACY_DEFAULT_AHK_QDIR = r"C:\Users\davey\Desktop\Quick Launch Build Scripts"
DEFAULT_AHK_QDIR = str(Path.home() / "Desktop" / "Quick Launch Build Scripts")
CONFIG_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_DATA_DIR_NAME / CONFIG_FILENAME


def default_ahk_qdir() -> str:
    return DEFAULT_AHK_QDIR


def default_config_file() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / APP_DATA_DIR_NAME / CONFIG_FILENAME


@dataclass
class ManagedItem:
    name: str
    path: str
    item_type: str
    group: str | None = None
    pid: int | None = None
    managed: bool = True


@dataclass
class AppConfig:
    managed_items: list[ManagedItem] = field(default_factory=list)
    exclusive_groups: dict[str, list[str]] = field(default_factory=dict)
    show_unmanaged_ahk: bool = True
    refresh_interval_ms: int = 1000
    ahk_qdir_path: str = field(default_factory=default_ahk_qdir)


class ConfigStore:
    def __init__(
        self,
        path: Path | str | None = None,
        legacy_path: Path | str | None = LEGACY_CONFIG_FILE,
    ) -> None:
        self.path = Path(path) if path is not None else default_config_file()
        self.legacy_path = Path(legacy_path) if path is None and legacy_path is not None else None

    def load(self) -> AppConfig:
        if not self.path.exists():
            source = self._migration_source()
            config = self._read_config(source) if source else AppConfig()
            if self._is_default_ahk_qdir(config.ahk_qdir_path):
                self._ensure_default_ahk_qdir(config)
            self.save(config)
            return config

        config = self._read_config(self.path)
        if self._is_default_ahk_qdir(config.ahk_qdir_path):
            self._ensure_default_ahk_qdir(config)
        return config

    def save(self, config: AppConfig) -> None:
        data: dict[str, Any] = {
            "managed_items": [asdict(item) for item in config.managed_items],
            "exclusive_groups": config.exclusive_groups,
            "show_unmanaged_ahk": config.show_unmanaged_ahk,
            "refresh_interval_ms": config.refresh_interval_ms,
            "ahk_qdir_path": config.ahk_qdir_path,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_config(self, path: Path) -> AppConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_ahk_qdir = str(raw.get("ahk_qdir_path", default_ahk_qdir()))
        using_default_qdir = self._is_default_ahk_qdir(raw_ahk_qdir) or "ahk_qdir_path" not in raw
        return AppConfig(
            managed_items=[ManagedItem(**item) for item in raw.get("managed_items", [])],
            exclusive_groups=dict(raw.get("exclusive_groups", {})),
            show_unmanaged_ahk=bool(raw.get("show_unmanaged_ahk", True)),
            refresh_interval_ms=int(raw.get("refresh_interval_ms", 1000)),
            ahk_qdir_path=default_ahk_qdir() if using_default_qdir else raw_ahk_qdir,
        )

    def _migration_source(self) -> Path | None:
        if self.legacy_path is None or not self.legacy_path.exists():
            return None
        if self.legacy_path.resolve() == self.path.resolve():
            return None
        return self.legacy_path

    def _ensure_default_ahk_qdir(self, config: AppConfig) -> None:
        Path(config.ahk_qdir_path).mkdir(parents=True, exist_ok=True)

    def _is_default_ahk_qdir(self, path: str) -> bool:
        normalized = Path(path).as_posix().casefold()
        return normalized in {
            Path(default_ahk_qdir()).as_posix().casefold(),
            Path(LEGACY_DEFAULT_AHK_QDIR).as_posix().casefold(),
        }
