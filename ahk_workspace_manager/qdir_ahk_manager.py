from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import psutil


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

    def scan(self, directory: str) -> list[QdirAhkScript]:
        root = Path(directory)
        if not root.exists() or not root.is_dir():
            return []
        return [
            QdirAhkScript(name=path.name, path=str(path))
            for path in sorted(root.glob("*.ahk"), key=lambda item: item.name.lower())
            if path.is_file()
        ]

    def states(self, directory: str) -> list[QdirAhkState]:
        scripts = self.scan(directory)
        running = self.running_script_pids(scripts)
        states: list[QdirAhkState] = []
        for script in scripts:
            key = self.normalize_path(script.path)
            pid = running.get(key)
            if pid:
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
        self.failed_paths.discard(target_key)
        return True

    def stop(self, script: QdirAhkScript) -> bool:
        pid = self.running_script_pids([script]).get(self.normalize_path(script.path))
        if not pid:
            return False
        stopped = self.stop_pid(pid)
        if stopped:
            self.failed_paths.discard(self.normalize_path(script.path))
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

    def normalize_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve()).casefold()
        except OSError:
            return str(Path(path).absolute()).casefold()

    def _default_process_provider(self):
        return psutil.process_iter(["pid", "name", "exe", "cmdline"])

    def _default_launcher(self, path: str) -> object:
        return subprocess.Popen(f'"{path}"', shell=True)

