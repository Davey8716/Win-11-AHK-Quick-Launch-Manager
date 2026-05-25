from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import AppConfig, TaskbarItem


class TaskbarManager:
    def __init__(self, config: AppConfig, pinned_dir: Path | str | None = None) -> None:
        self.config = config
        self.pinned_dir = Path(pinned_dir) if pinned_dir else self._default_pinned_dir()

    def add_path(self, path: str) -> list[TaskbarItem]:
        candidates = self._resolve_candidates(Path(path))
        added: list[TaskbarItem] = []
        known = {Path(item.path).resolve().as_posix().lower() for item in self.config.taskbar_items if Path(item.path).exists()}

        for candidate in candidates:
            key = candidate.resolve().as_posix().lower()
            if key in known:
                continue
            item = TaskbarItem(name=self.display_name(candidate), path=str(candidate), pinned=False)
            item.pinned = self.pin(item.path)
            self.config.taskbar_items.append(item)
            known.add(key)
            added.append(item)

        return added

    def remove(self, item: TaskbarItem) -> None:
        self.config.taskbar_items = [existing for existing in self.config.taskbar_items if existing.path != item.path]

    def remove_all(self) -> None:
        self.config.taskbar_items.clear()

    def pin_all(self) -> None:
        for item in self.config.taskbar_items:
            item.pinned = self.pin(item.path)

    def unpin_all(self) -> None:
        for item in self.config.taskbar_items:
            item.pinned = not self.unpin(item.path)

    def pin(self, path: str) -> bool:
        return self._invoke_visible_taskbar_verb(path, "pin") or self._invoke_known_taskbar_verb(path, "pin") or self._create_pinned_shortcut(path)

    def unpin(self, path: str) -> bool:
        return self._invoke_visible_taskbar_verb(path, "unpin") or self._invoke_known_taskbar_verb(path, "unpin") or self._remove_pinned_shortcut(path)

    def _resolve_candidates(self, path: Path) -> list[Path]:
        if path.is_dir():
            return sorted(path.rglob("*.exe"))
        if path.suffix.lower() in {".exe", ".lnk"}:
            return [path]
        return []

    def display_name(self, path: Path) -> str:
        if path.suffix.lower() == ".lnk":
            return path.stem
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _default_pinned_dir(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return Path.home() / "AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"
        return Path(appdata) / "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"

    def pinned_shortcut_path(self, path: str) -> Path:
        target = Path(path)
        return self.pinned_dir / f"{target.stem}.lnk"

    def _invoke_visible_taskbar_verb(self, path: str, action: str) -> bool:
        item = self._shell_item(path)
        if item is None:
            return False

        expected = "pintotaskbar" if action == "pin" else "unpinfromtaskbar"
        try:
            for verb in item.Verbs():
                name = self._normalize_verb_name(verb.Name)
                if name == expected:
                    verb.DoIt()
                    return self._taskbar_state_matches(path, action)
        except Exception:
            return False
        return False

    def _invoke_known_taskbar_verb(self, path: str, action: str) -> bool:
        verbs = ("taskbarpin", "pintotaskbar") if action == "pin" else ("taskbarunpin", "unpinfromtaskbar")
        return any(self._invoke_taskbar_verb(path, verb_name) for verb_name in verbs)

    def _invoke_taskbar_verb(self, path: str, verb_name: str) -> bool:
        item = self._shell_item(path)
        if item is None:
            return False

        try:
            item.InvokeVerbEx(verb_name)
            return self._taskbar_state_matches(path, "pin" if "pin" in verb_name and "unpin" not in verb_name else "unpin")
        except Exception:
            return False

    def _shell_item(self, path: str):
        target = Path(path)
        if not target.exists():
            return None

        try:
            import win32com.client

            shell_app = win32com.client.Dispatch("Shell.Application")
            folder = shell_app.Namespace(str(target.parent))
            return folder.ParseName(target.name) if folder else None
        except Exception:
            return None

    def _normalize_verb_name(self, name: str) -> str:
        return "".join(char for char in name.replace("&", "").lower() if char.isalnum())

    def _create_pinned_shortcut(self, path: str) -> bool:
        target = Path(path)
        if not target.exists() or target.suffix.lower() not in {".exe", ".lnk"}:
            return False
        self.pinned_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = self.pinned_shortcut_path(path)

        try:
            if target.suffix.lower() == ".lnk":
                shutil.copy2(target, shortcut_path)
                return shortcut_path.exists()

            import win32com.client

            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(str(shortcut_path))
            shortcut.TargetPath = str(target)
            shortcut.WorkingDirectory = str(target.parent)
            shortcut.IconLocation = str(target)
            shortcut.Save()
            return shortcut_path.exists()
        except Exception:
            return False

    def _remove_pinned_shortcut(self, path: str) -> bool:
        shortcut_path = self.pinned_shortcut_path(path)
        if not shortcut_path.exists():
            return False
        try:
            shortcut_path.unlink()
            return True
        except OSError:
            return False

    def _taskbar_state_matches(self, path: str, action: str) -> bool:
        shortcut_exists = self.pinned_shortcut_path(path).exists()
        return shortcut_exists if action == "pin" else not shortcut_exists
