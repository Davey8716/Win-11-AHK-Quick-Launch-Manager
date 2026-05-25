from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil

from .config import AppConfig, ManagedItem
from .tray_monitor import TRAY_STATUS, TrayIcon, TrayIconMonitor


ESSENTIAL_PROCESSES = {
    "csrss.exe",
    "dwm.exe",
    "explorer.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "svchost.exe",
    "system",
    "wininit.exe",
    "winlogon.exe",
}


@dataclass
class ProcessState:
    item: ManagedItem
    status: str
    pid: int | None
    can_stop: bool = False


class ProcessManager:
    def __init__(self, config: AppConfig, tray_monitor: TrayIconMonitor | None = None) -> None:
        self.config = config
        self.tray_monitor = tray_monitor or TrayIconMonitor()

    def register_path(self, path: str, group: str | None = None) -> list[ManagedItem]:
        source = Path(path)
        candidates = self._resolve_candidates(source)
        added: list[ManagedItem] = []
        known = {Path(item.path).resolve().as_posix().lower() for item in self.config.managed_items if Path(item.path).exists()}

        for candidate in candidates:
            key = candidate.resolve().as_posix().lower()
            if key in known:
                continue
            item_type = "AHK" if candidate.suffix.lower() == ".ahk" else "APP"
            item = ManagedItem(name=candidate.name, path=str(candidate), item_type=item_type, group=group)
            self.config.managed_items.append(item)
            added.append(item)
            known.add(key)

        return added

    def poll(self) -> list[ProcessState]:
        states: list[ProcessState] = []
        for item in self.config.managed_items:
            pid = self.find_pid(item)
            item.pid = pid
            states.append(ProcessState(item=item, status="RUNNING" if pid else "STOPPED", pid=pid, can_stop=bool(pid)))

        if self.config.show_unmanaged_ahk:
            managed_paths = {Path(item.path).resolve().as_posix().lower() for item in self.config.managed_items if Path(item.path).exists()}
            for proc in self._iter_processes():
                script = self._ahk_script_from_process(proc)
                if not script:
                    continue
                script_path = Path(script)
                if script_path.exists() and script_path.resolve().as_posix().lower() in managed_paths:
                    continue
                states.append(
                    ProcessState(
                        item=ManagedItem(
                            name=script_path.name,
                            path=str(script_path),
                            item_type="AHK",
                            managed=False,
                        ),
                        status="RUNNING",
                        pid=proc.info.get("pid"),
                        can_stop=self._can_terminate_pid(proc.info.get("pid")),
                    )
                )

        states.extend(self._tray_states(states))
        return states

    def launch(self, item: ManagedItem) -> int | None:
        path = Path(item.path)
        if not path.exists():
            return None

        if path.suffix.lower() == ".ahk":
            os.startfile(str(path))
            return None

        proc = subprocess.Popen([str(path)], cwd=str(path.parent))
        item.pid = proc.pid
        return proc.pid

    def terminate(self, item: ManagedItem) -> bool:
        if not item.managed and item.pid:
            return self.terminate_pid(item.pid)
        pid = self.find_pid(item)
        if not pid:
            return False
        return self.terminate_pid(pid)

    def terminate_pid(self, pid: int) -> bool:
        try:
            proc = psutil.Process(pid)
            if proc.name().lower() in ESSENTIAL_PROCESSES:
                return False
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except psutil.TimeoutExpired:
                proc.kill()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def kill_all_managed(self) -> int:
        killed = 0
        for item in self.config.managed_items:
            if self.terminate(item):
                killed += 1
        return killed

    def restart(self, item: ManagedItem) -> None:
        self.terminate(item)
        self.launch(item)

    def find_pid(self, item: ManagedItem) -> int | None:
        item_path = Path(item.path)
        item_key = item_path.resolve().as_posix().lower() if item_path.exists() else item.path.lower()
        for proc in self._iter_processes():
            if item.item_type == "AHK":
                script = self._ahk_script_from_process(proc)
                if script and Path(script).exists() and Path(script).resolve().as_posix().lower() == item_key:
                    return proc.info.get("pid")
            else:
                exe = proc.info.get("exe")
                if exe and Path(exe).exists() and Path(exe).resolve().as_posix().lower() == item_key:
                    return proc.info.get("pid")
        return None

    def _resolve_candidates(self, path: Path) -> list[Path]:
        if path.is_dir():
            return sorted([*path.rglob("*.ahk"), *path.rglob("*.exe")])
        if path.suffix.lower() in {".ahk", ".exe"}:
            return [path]
        return []

    def _iter_processes(self):
        yield from psutil.process_iter(["pid", "name", "exe", "cmdline"])

    def _ahk_script_from_process(self, proc: psutil.Process) -> str | None:
        name = (proc.info.get("name") or "").lower()
        if "autohotkey" not in name:
            return None
        for part in proc.info.get("cmdline") or []:
            if part.lower().endswith(".ahk"):
                return part
        return None

    def _tray_states(self, existing_states: list[ProcessState]) -> list[ProcessState]:
        icons, fallback_message = self._tray_icons()
        seen_pids = {state.pid for state in existing_states if state.pid}
        seen_paths = {Path(state.item.path).resolve().as_posix().lower() for state in existing_states if state.item.path and Path(state.item.path).exists()}
        states: list[ProcessState] = []

        if fallback_message:
            states.append(
                ProcessState(
                    item=ManagedItem(
                        name=fallback_message,
                        path="",
                        item_type=TRAY_STATUS,
                        managed=False,
                    ),
                    status="INFO",
                    pid=None,
                    can_stop=False,
                )
            )

        for icon in icons:
            path_key = Path(icon.path).resolve().as_posix().lower() if icon.path and Path(icon.path).exists() else ""
            if icon.pid and icon.pid in seen_pids:
                continue
            if path_key and path_key in seen_paths:
                continue
            item = ManagedItem(
                name=icon.name,
                path=icon.path,
                item_type=icon.source,
                pid=icon.pid,
                managed=False,
            )
            states.append(ProcessState(item=item, status="RUNNING", pid=icon.pid, can_stop=self._can_terminate_pid(icon.pid)))
            if icon.pid:
                seen_pids.add(icon.pid)
            if path_key:
                seen_paths.add(path_key)
        return states

    def _tray_icons(self) -> tuple[list[TrayIcon], str | None]:
        try:
            result = self.tray_monitor.scan()
        except Exception:
            return [], "Tray enumeration unavailable - showing likely tray/background apps"
        message = result.message if result.mode == "fallback" else None
        return result.icons, message

    def _can_terminate_pid(self, pid: int | None) -> bool:
        if not pid:
            return False
        try:
            return psutil.Process(pid).name().lower() not in ESSENTIAL_PROCESSES
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
