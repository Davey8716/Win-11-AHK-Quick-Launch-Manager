from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONFIG_FILE = Path("workspace_manager.json")
LEGACY_DEFAULT_AHK_QDIR = r"C:\Users\davey\Desktop\Quick Launch Build Scripts"
DEFAULT_AHK_QDIR = str(Path.home() / "Desktop" / "Quick Launch Build Scripts")


def default_ahk_qdir() -> str:
    return DEFAULT_AHK_QDIR


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
    def __init__(self, path: Path | str = CONFIG_FILE) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            config = AppConfig()
            self._ensure_default_ahk_qdir(config)
            return config

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw_ahk_qdir = str(raw.get("ahk_qdir_path", default_ahk_qdir()))
        using_default_qdir = self._is_default_ahk_qdir(raw_ahk_qdir) or "ahk_qdir_path" not in raw
        config = AppConfig(
            managed_items=[ManagedItem(**item) for item in raw.get("managed_items", [])],
            exclusive_groups=dict(raw.get("exclusive_groups", {})),
            show_unmanaged_ahk=bool(raw.get("show_unmanaged_ahk", True)),
            refresh_interval_ms=int(raw.get("refresh_interval_ms", 1000)),
            ahk_qdir_path=default_ahk_qdir() if using_default_qdir else raw_ahk_qdir,
        )
        if using_default_qdir:
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
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _ensure_default_ahk_qdir(self, config: AppConfig) -> None:
        Path(config.ahk_qdir_path).mkdir(parents=True, exist_ok=True)

    def _is_default_ahk_qdir(self, path: str) -> bool:
        normalized = Path(path).as_posix().casefold()
        return normalized in {
            Path(default_ahk_qdir()).as_posix().casefold(),
            Path(LEGACY_DEFAULT_AHK_QDIR).as_posix().casefold(),
        }
