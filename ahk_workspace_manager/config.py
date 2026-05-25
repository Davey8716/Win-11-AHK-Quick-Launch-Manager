from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONFIG_FILE = Path("workspace_manager.json")


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


class ConfigStore:
    def __init__(self, path: Path | str = CONFIG_FILE) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return AppConfig(
            managed_items=[ManagedItem(**item) for item in raw.get("managed_items", [])],
            exclusive_groups=dict(raw.get("exclusive_groups", {})),
            show_unmanaged_ahk=bool(raw.get("show_unmanaged_ahk", True)),
            refresh_interval_ms=int(raw.get("refresh_interval_ms", 1000)),
        )

    def save(self, config: AppConfig) -> None:
        data: dict[str, Any] = {
            "managed_items": [asdict(item) for item in config.managed_items],
            "exclusive_groups": config.exclusive_groups,
            "show_unmanaged_ahk": config.show_unmanaged_ahk,
            "refresh_interval_ms": config.refresh_interval_ms,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
