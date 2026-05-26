from __future__ import annotations
from pathlib import Path
from .config import AppConfig, ManagedItem
from .process_manager import ProcessManager


class AHKManager:
    def __init__(self, config: AppConfig, process_manager: ProcessManager) -> None:
        self.config = config
        self.process_manager = process_manager

    def start(self, item: ManagedItem) -> None:
        group_name = self.group_for(item)
        if group_name:
            group_members = {member.lower() for member in self.config.exclusive_groups.get(group_name, [])}
            for other in self.config.managed_items:
                if other.path == item.path:
                    continue
                if other.item_type != "AHK":
                    continue
                if self._matches_group_member(other, group_members):
                    self.process_manager.terminate(other)

        self.process_manager.launch(item)

    def group_for(self, item: ManagedItem) -> str | None:
        if item.group:
            return item.group
        name = Path(item.path).name.lower()
        for group_name, members in self.config.exclusive_groups.items():
            if name in {member.lower() for member in members}:
                return group_name
        return None

    def set_group(self, item: ManagedItem, group_name: str | None) -> None:
        item.group = group_name or None
        if not group_name:
            return
        members = self.config.exclusive_groups.setdefault(group_name, [])
        script_name = Path(item.path).name
        if script_name not in members:
            members.append(script_name)

    def _matches_group_member(self, item: ManagedItem, group_members: set[str]) -> bool:
        if item.group and item.group in self.config.exclusive_groups:
            return Path(item.path).name.lower() in group_members or item.group == self.group_for(item)
        return Path(item.path).name.lower() in group_members

