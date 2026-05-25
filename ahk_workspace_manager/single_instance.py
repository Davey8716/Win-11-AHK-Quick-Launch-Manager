from __future__ import annotations


MUTEX_NAME = "Local\\AHKWorkspaceManagerSingleInstance"


class SingleInstanceGuard:
    def __init__(self, mutex_name: str = MUTEX_NAME) -> None:
        self.mutex_name = mutex_name
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
        return not self.already_running

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            import win32api

            win32api.CloseHandle(self.handle)
        finally:
            self.handle = None

