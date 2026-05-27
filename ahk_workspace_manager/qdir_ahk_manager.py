from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import psutil

PROJECTS_ROOT = Path.home() / "Desktop" / "Projects"
INVALID_WINDOWS_FILENAME_CHARS = '<>:"/\\|?*'


class QdirAhkCreateError(Exception):
    pass


@dataclass(frozen=True)
class QdirAhkScript:
    name: str
    path: str


@dataclass(frozen=True)
class QdirAhkState:
    script: QdirAhkScript
    status: str
    pid: int | None = None


ProcessProvider = Callable[[], Iterable]
Launcher = Callable[[str], object]


class QdirAhkManager:
    def __init__(
        self,
        process_provider: ProcessProvider | None = None,
        launcher: Launcher | None = None,
    ) -> None:
        self.process_provider = process_provider or self._default_process_provider
        self.launcher = launcher or self._default_launcher
        self.failed_paths: set[str] = set()
        self.active_script_path: str | None = None

    def scan(self, directory: str) -> list[QdirAhkScript]:
        root = Path(directory)
        if not root.exists() or not root.is_dir():
            return []
        return [
            QdirAhkScript(name=path.name, path=str(path))
            for path in sorted(root.glob("*.ahk"), key=lambda item: item.name.lower())
            if path.is_file()
        ]

    def create_project_launcher(self, project_dir: str, qdir_dir: str) -> QdirAhkScript:
        project_root = Path(project_dir).resolve()
        qdir_root = Path(qdir_dir).resolve()
        if not qdir_root.exists() or not qdir_root.is_dir():
            raise QdirAhkCreateError("The picked AHK directory does not exist.")

        project_file = project_root / "main.py"
        if not project_file.exists() or not project_file.is_file():
            raise QdirAhkCreateError("The selected project does not contain main.py.")

        filename_stem = self._project_launcher_filename_stem(project_root)
        if not filename_stem:
            raise QdirAhkCreateError("Could not create a valid AHK filename for this project.")

        target_path = qdir_root / f"{filename_stem}.ahk"
        if target_path.exists():
            raise QdirAhkCreateError(f"{target_path.name} already exists.")

        target_path.write_text(self._project_launcher_content(project_file), encoding="utf-8")
        return QdirAhkScript(name=target_path.name, path=str(target_path))

    def states(self, directory: str) -> list[QdirAhkState]:
        scripts = self.scan(directory)
        running = self.running_script_pids(scripts)
        active_key = self._visual_active_key(running)
        states: list[QdirAhkState] = []
        for script in scripts:
            key = self.normalize_path(script.path)
            pid = running.get(key)
            if pid and key == active_key:
                self.failed_paths.discard(key)
                states.append(QdirAhkState(script=script, status="RUNNING", pid=pid))
            elif key in self.failed_paths:
                states.append(QdirAhkState(script=script, status="FAILED"))
            else:
                states.append(QdirAhkState(script=script, status="STOPPED"))
        return states

    def start(self, script: QdirAhkScript, directory: str) -> bool:
        target_key = self.normalize_path(script.path)
        for other in self.states(directory):
            other_key = self.normalize_path(other.script.path)
            if other.pid and other_key != target_key:
                self.stop_pid(other.pid)

        try:
            self.launcher(script.path)
        except Exception:
            self.failed_paths.add(target_key)
            return False
        self.active_script_path = target_key
        self.failed_paths.discard(target_key)
        return True

    def stop(self, script: QdirAhkScript) -> bool:
        pid = self.running_script_pids([script]).get(self.normalize_path(script.path))
        if not pid:
            return False
        stopped = self.stop_pid(pid)
        if stopped:
            key = self.normalize_path(script.path)
            self.failed_paths.discard(key)
            if self.active_script_path == key:
                self.active_script_path = None
        return stopped

    def stop_pid(self, pid: int) -> bool:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except psutil.TimeoutExpired:
                proc.kill()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def running_script_pids(self, scripts: list[QdirAhkScript]) -> dict[str, int]:
        script_keys = {self.normalize_path(script.path) for script in scripts}
        running: dict[str, int] = {}
        for proc in self.process_provider():
            info = getattr(proc, "info", {})
            pid = info.get("pid")
            for arg in info.get("cmdline") or []:
                key = self.normalize_path(arg)
                if key in script_keys and pid:
                    running[key] = pid
        return running

    def _visual_active_key(self, running: dict[str, int]) -> str | None:
        if self.active_script_path and self.active_script_path in running:
            return self.active_script_path
        if self.active_script_path and self.active_script_path not in running:
            self.active_script_path = None
        if len(running) == 1:
            self.active_script_path = next(iter(running))
            return self.active_script_path
        if len(running) > 1:
            self.active_script_path = next(reversed(running))
            return self.active_script_path
        return None

    def normalize_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve()).casefold()
        except OSError:
            return str(Path(path).absolute()).casefold()

    def _project_launcher_filename_stem(self, project_root: Path) -> str:
        try:
            relative = project_root.relative_to(PROJECTS_ROOT.resolve())
            raw_name = " - ".join(relative.parts)
        except ValueError:
            raw_name = project_root.name
        return self._sanitize_filename_stem(raw_name)

    def _sanitize_filename_stem(self, name: str) -> str:
        sanitized = "".join("_" if char in INVALID_WINDOWS_FILENAME_CHARS else char for char in name)
        sanitized = sanitized.strip().strip(".")
        return sanitized

    def _project_launcher_content(self, project_file: Path) -> str:
        project_path = str(project_file)
        return (
            "#Requires AutoHotkey v1.1\n\n"
            f'project := "{project_path}"\n\n'
            "^XButton1::\n"
            'Run, wt.exe python "%project%"\n'
            "return\n\n"
            "XButton2::\n"
            'Run, pythonw.exe "%project%"\n'
            "return\n\n"
            "XButton1::\n"
            "Run, taskkill /IM pythonw.exe /F\n"
            "return\n"
        )

    def _default_process_provider(self):
        return psutil.process_iter(["pid", "name", "exe", "cmdline"])

    def _default_launcher(self, path: str) -> object:
        return subprocess.Popen(f'"{path}"', shell=True)
