from __future__ import annotations


MUTEX_NAME = "Local\\AHKWorkspaceManagerSingleInstance"
WINDOW_TITLE = "Tray Manager"
WM_APP_RESTORE_INSTANCE = 0x8001


class SingleInstanceGuard:
    def __init__(
        self,
        mutex_name: str = MUTEX_NAME,
        window_title: str = WINDOW_TITLE,
        restore_message: int = WM_APP_RESTORE_INSTANCE,
    ) -> None:
        self.mutex_name = mutex_name
        self.window_title = window_title
        self.restore_message = restore_message
        self.handle = None
        self.already_running = False

    def acquire(self) -> bool:
        try:
            import win32api
            import win32event
            import winerror
        except ImportError:
            return True

        self.handle = win32event.CreateMutex(None, False, self.mutex_name)
        self.already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        if self.already_running:
            self.bring_existing_instance_to_front()
        return not self.already_running

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            import win32api

            win32api.CloseHandle(self.handle)
        finally:
            self.handle = None

    def bring_existing_instance_to_front(self) -> None:
        try:
            import win32gui
        except ImportError:
            return

        target_hwnd = None

        def enum_handler(hwnd, _):
            nonlocal target_hwnd
            try:
                title = win32gui.GetWindowText(hwnd)
            except Exception:
                return True

            if self.window_title in title and hwnd != 0:
                target_hwnd = hwnd

            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            return

        if not target_hwnd:
            return

        try:
            win32gui.PostMessage(target_hwnd, self.restore_message, 0, 0)
        except Exception:
            return
