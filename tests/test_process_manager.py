import os
import sys

from ahk_workspace_manager.config import AppConfig, ManagedItem
from ahk_workspace_manager.process_manager import ProcessManager
from ahk_workspace_manager.tray_monitor import TRAY_DETECTED, TRAY_OVERFLOW, TRAY_STATUS, TRAY_VISIBLE, TrayIcon, TrayMonitorResult


class FakeTrayMonitor:
    def __init__(self, icons=None, fallback=None):
        self.icons = icons or []
        self.fallback = fallback or []

    def list_icons(self):
        return self.icons

    def fallback_icons(self):
        return self.fallback

    def scan(self):
        if self.icons:
            return TrayMonitorResult(icons=self.icons, mode="live")
        return TrayMonitorResult(
            icons=self.fallback,
            mode="fallback",
            message="Tray enumeration unavailable - showing likely tray/background apps",
        )


def test_tray_icons_are_merged_and_deduped_by_path(tmp_path):
    managed_exe = tmp_path / "managed.exe"
    managed_exe.write_text("", encoding="utf-8")
    config = AppConfig(
        managed_items=[ManagedItem(name="Managed", path=str(managed_exe), item_type="APP")],
        show_unmanaged_ahk=False,
    )
    monitor = FakeTrayMonitor(
        icons=[
            TrayIcon(name="Duplicate", source=TRAY_VISIBLE, path=str(managed_exe)),
            TrayIcon(name="Python", source=TRAY_OVERFLOW, pid=os.getpid(), path=sys.executable),
        ]
    )
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    assert [state.item.name for state in states] == ["Managed", "Python"]
    assert states[1].item.managed is False
    assert states[1].item.item_type == TRAY_OVERFLOW


def test_fallback_icons_are_used_when_live_tray_monitor_is_empty():
    config = AppConfig(show_unmanaged_ahk=False)
    monitor = FakeTrayMonitor(fallback=[TrayIcon(name="Fallback", source=TRAY_DETECTED, pid=os.getpid(), path=sys.executable)])
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    assert len(states) == 2
    assert states[0].item.item_type == TRAY_STATUS
    assert states[0].can_stop is False
    assert states[1].item.name == "Fallback"
    assert states[1].item.item_type == TRAY_DETECTED


def test_live_tray_icons_do_not_emit_fallback_status():
    config = AppConfig(show_unmanaged_ahk=False)
    monitor = FakeTrayMonitor(icons=[TrayIcon(name="Live", source=TRAY_VISIBLE, pid=os.getpid(), path=sys.executable)])
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    assert [state.item.item_type for state in states] == [TRAY_VISIBLE]


def test_poll_sorts_process_rows_alphabetically(tmp_path):
    beta = tmp_path / "Beta.exe"
    beta.write_text("", encoding="utf-8")
    config = AppConfig(
        managed_items=[ManagedItem(name="Beta", path=str(beta), item_type="APP")],
        show_unmanaged_ahk=False,
    )
    monitor = FakeTrayMonitor(icons=[TrayIcon(name="alpha", source=TRAY_VISIBLE, pid=os.getpid(), path=sys.executable)])
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    assert [state.item.name for state in states] == ["alpha", "Beta"]


def test_fallback_status_row_stays_before_alphabetized_rows():
    config = AppConfig(show_unmanaged_ahk=False)
    monitor = FakeTrayMonitor(
        fallback=[
            TrayIcon(name="Zulu", source=TRAY_DETECTED, pid=os.getpid(), path=sys.executable),
            TrayIcon(name="Alpha", source=TRAY_DETECTED, pid=None, path=""),
        ]
    )
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    assert states[0].item.item_type == TRAY_STATUS
    assert [state.item.name for state in states[1:]] == ["Alpha", "Zulu"]


def test_unmanaged_tray_stop_requires_pid():
    config = AppConfig(show_unmanaged_ahk=False)
    monitor = FakeTrayMonitor(
        icons=[
            TrayIcon(name="No Pid", source=TRAY_VISIBLE),
            TrayIcon(name="Current Process", source=TRAY_VISIBLE, pid=os.getpid(), path=sys.executable),
        ]
    )
    manager = ProcessManager(config, tray_monitor=monitor)

    states = manager.poll()

    by_name = {state.item.name: state for state in states}
    assert by_name["No Pid"].can_stop is False
    assert by_name["Current Process"].can_stop is True
