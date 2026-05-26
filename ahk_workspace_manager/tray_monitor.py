from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

TRAY_VISIBLE = "TRAY_VISIBLE"
TRAY_OVERFLOW = "TRAY_OVERFLOW"
TRAY_DETECTED = "TRAY_DETECTED"
TRAY_STATUS = "TRAY_STATUS"

TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TB_GETBUTTONTEXTW = 0x044B

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

KNOWN_TRAY_PROCESS_NAMES = {
    "autohotkey.exe",
    "discord.exe",
    "dropbox.exe",
    "googledrivefs.exe",
    "ms-teams.exe",
    "onedrive.exe",
    "slack.exe",
    "steam.exe",
    "teams.exe",
    "telegram.exe",
    "whatsapp.exe",
}

NOISY_PROCESS_NAMES = {
    "aggregatorhost.exe",
    "audiodg.exe",
    "backgroundtaskhost.exe",
    "conhost.exe",
    "dllhost.exe",
    "fontdrvhost.exe",
    "lockapp.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "securityhealthservice.exe",
    "shellexperiencehost.exe",
    "sihost.exe",
    "startmenuexperiencehost.exe",
    "taskhostw.exe",
    "textinputhost.exe",
    "wudfhost.exe",
}

NOISY_NAME_PARTS = (
    "service",
    "helper",
    "crashpad",
    "updater",
)

SYSTEM_PROCESS_NAMES = {
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

GUI_APP_PATH_PARTS = (
    "\\appdata\\local\\",
    "\\appdata\\roaming\\",
    "\\program files\\",
    "\\program files (x86)\\",
)


@dataclass(frozen=True)
class TrayMonitorResult:
    icons: list["TrayIcon"]
    mode: str
    message: str = ""


class TBBUTTON(ctypes.Structure):
    _fields_ = [
        ("iBitmap", ctypes.c_int),
        ("idCommand", ctypes.c_int),
        ("fsState", ctypes.c_ubyte),
        ("fsStyle", ctypes.c_ubyte),
        ("bReserved", ctypes.c_ubyte * (6 if ctypes.sizeof(ctypes.c_void_p) == 8 else 2)),
        ("dwData", ctypes.c_void_p),
        ("iString", ctypes.c_void_p),
    ]


class TRAYDATA(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint),
        ("reserved0", ctypes.c_uint),
        ("reserved1", ctypes.c_uint),
        ("hIcon", ctypes.c_void_p),
    ]


@dataclass(frozen=True)
class TrayIcon:
    name: str
    source: str
    pid: int | None = None
    path: str = ""


class TrayIconMonitor:
    def scan(self) -> TrayMonitorResult:
        try:
            icons = self.list_icons()
        except Exception as exc:
            icons = []
            message = f"Tray enumeration failed: {exc}"
        else:
            message = "Tray enumeration unavailable - showing likely tray/background apps"
        if icons:
            return TrayMonitorResult(icons=icons, mode="live")

        return TrayMonitorResult(icons=self.fallback_icons(), mode="fallback", message=message)

    def list_icons(self) -> list[TrayIcon]:
        icons = [*self._toolbar_icons("Shell_TrayWnd", TRAY_VISIBLE), *self._toolbar_icons("NotifyIconOverflowWindow", TRAY_OVERFLOW)]
        return self._dedupe(icons)

    def fallback_icons(self) -> list[TrayIcon]:
        icons: list[TrayIcon] = []
        seen_paths: set[str] = set()
        window_pids = self._window_process_ids()
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                name = proc.info.get("name") or ""
                exe = proc.info.get("exe") or ""
                if not self._is_fallback_candidate(proc.info, window_pids):
                    continue
                exe_key = exe.lower()
                if exe_key in seen_paths:
                    continue
                seen_paths.add(exe_key)
                icons.append(
                    TrayIcon(
                        name=Path(exe).stem if exe else name,
                        source=TRAY_DETECTED,
                        pid=proc.info.get("pid"),
                        path=exe,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return self._dedupe(icons)

    def _is_fallback_candidate(self, proc_info: dict[str, Any], window_pids: set[int]) -> bool:
        pid = proc_info.get("pid")
        name = (proc_info.get("name") or "").lower()
        exe = proc_info.get("exe") or ""
        exe_lower = exe.lower()
        cmdline = " ".join(proc_info.get("cmdline") or []).lower()

        if not pid or not exe:
            return False
        if name in SYSTEM_PROCESS_NAMES or name in NOISY_PROCESS_NAMES:
            return False
        if "\\windows\\system32\\" in exe_lower or "\\windows\\syswow64\\" in exe_lower:
            return name in KNOWN_TRAY_PROCESS_NAMES
        if name in KNOWN_TRAY_PROCESS_NAMES:
            return True
        if "autohotkey" in name or ".ahk" in cmdline:
            return True
        if pid in window_pids:
            return True
        if any(part in name for part in NOISY_NAME_PARTS):
            return False
        return any(part in exe_lower for part in GUI_APP_PATH_PARTS) and self._looks_like_user_app_path(exe_lower)

    def _looks_like_user_app_path(self, exe_lower: str) -> bool:
        noisy_path_parts = (
            "\\common files\\",
            "\\node_modules\\",
            "\\python\\",
            "\\windowsapps\\microsoft.",
        )
        return not any(part in exe_lower for part in noisy_path_parts)

    def _window_process_ids(self) -> set[int]:
        try:
            import win32gui
            import win32process
        except ImportError:
            return set()

        pids: set[int] = set()

        def visit(hwnd: int, _extra) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).strip():
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        pids.add(pid)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(visit, None)
        except Exception:
            return set()
        return pids

    def _toolbar_icons(self, root_class: str, source: str) -> list[TrayIcon]:
        try:
            import win32gui
            import win32process
        except ImportError:
            return []

        root = win32gui.FindWindow(root_class, None)
        if not root:
            return []

        icons: list[TrayIcon] = []
        for toolbar in self._child_windows_by_class(root, "ToolbarWindow32"):
            try:
                _, toolbar_pid = win32process.GetWindowThreadProcessId(toolbar)
                count = win32gui.SendMessage(toolbar, TB_BUTTONCOUNT, 0, 0)
            except Exception:
                continue

            icons.extend(self._toolbar_button_icons(toolbar, toolbar_pid, source, max(0, int(count))))
        return icons

    def _toolbar_button_icons(self, toolbar: int, toolbar_pid: int, source: str, count: int) -> list[TrayIcon]:
        try:
            import win32gui
            import win32process
        except ImportError:
            return []

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
        kernel32.VirtualAllocEx.restype = ctypes.c_void_p
        kernel32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        kernel32.ReadProcessMemory.restype = ctypes.c_bool
        kernel32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
        process = kernel32.OpenProcess(access, False, toolbar_pid)
        if not process:
            return []

        button_size = ctypes.sizeof(TBBUTTON)
        text_chars = 512
        allocation_type = MEM_COMMIT | MEM_RESERVE
        remote_button = kernel32.VirtualAllocEx(process, None, button_size, allocation_type, PAGE_READWRITE)
        remote_text = kernel32.VirtualAllocEx(process, None, text_chars * ctypes.sizeof(ctypes.c_wchar), allocation_type, PAGE_READWRITE)
        icons: list[TrayIcon] = []

        try:
            if not remote_button or not remote_text:
                return []

            for index in range(count):
                if not win32gui.SendMessage(toolbar, TB_GETBUTTON, index, remote_button):
                    continue
                button = self._read_struct(process, remote_button, TBBUTTON)
                if button is None:
                    continue

                owner_pid = toolbar_pid
                if button.dwData:
                    tray_data = self._read_struct(process, button.dwData, TRAYDATA)
                    if tray_data and tray_data.hwnd:
                        try:
                            _, owner_pid = win32process.GetWindowThreadProcessId(int(tray_data.hwnd))
                        except Exception:
                            owner_pid = toolbar_pid

                label = self._toolbar_button_text(toolbar, button.idCommand, process, remote_text, text_chars)
                path = self._process_path(owner_pid)
                name = label or Path(path).stem or f"Tray item {index + 1}"
                icons.append(TrayIcon(name=name, source=source, pid=owner_pid, path=path))
        finally:
            if remote_button:
                kernel32.VirtualFreeEx(process, remote_button, 0, MEM_RELEASE)
            if remote_text:
                kernel32.VirtualFreeEx(process, remote_text, 0, MEM_RELEASE)
            kernel32.CloseHandle(process)

        return icons

    def _child_windows_by_class(self, root: int, class_name: str) -> list[int]:
        import win32gui

        matches: list[int] = []

        def visit(hwnd: int) -> None:
            try:
                if win32gui.GetClassName(hwnd) == class_name:
                    matches.append(hwnd)
            except Exception:
                return
            child = win32gui.GetWindow(hwnd, win32gui.GW_CHILD)
            while child:
                visit(child)
                child = win32gui.GetWindow(child, win32gui.GW_HWNDNEXT)

        visit(root)
        return matches

    def _toolbar_button_text(self, toolbar: int, command_id: int, process: int, remote_text: int, text_chars: int) -> str:
        try:
            import win32gui

            result = win32gui.SendMessage(toolbar, TB_GETBUTTONTEXTW, command_id, remote_text)
            if result == -1:
                return ""
            buffer = ctypes.create_unicode_buffer(text_chars)
            bytes_read = ctypes.c_size_t()
            ctypes.windll.kernel32.ReadProcessMemory(
                process,
                remote_text,
                ctypes.byref(buffer),
                text_chars * ctypes.sizeof(ctypes.c_wchar),
                ctypes.byref(bytes_read),
            )
            return buffer.value.strip()
        except Exception:
            return ""

    def _read_struct(self, process: int, address: int, struct_type: type[Any]):
        data = struct_type()
        bytes_read = ctypes.c_size_t()
        ok = ctypes.windll.kernel32.ReadProcessMemory(
            process,
            address,
            ctypes.byref(data),
            ctypes.sizeof(data),
            ctypes.byref(bytes_read),
        )
        return data if ok else None

    def _process_path(self, pid: int | None) -> str:
        if not pid:
            return ""
        try:
            return psutil.Process(pid).exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return ""

    def _dedupe(self, icons: list[TrayIcon]) -> list[TrayIcon]:
        seen: set[tuple[int | None, str, str]] = set()
        unique: list[TrayIcon] = []
        for icon in icons:
            key = (icon.pid, icon.path.lower(), icon.name.lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(icon)
        return unique
