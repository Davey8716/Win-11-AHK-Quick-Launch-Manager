from PySide6.QtWidgets import QApplication, QToolButton

from ahk_workspace_manager.config import ManagedItem
from ahk_workspace_manager.process_manager import ProcessState
from ahk_workspace_manager.ui import ProcessRow


def app():
    existing = QApplication.instance()
    return existing or QApplication([])


def button_enabled(row: ProcessRow, text: str) -> bool:
    for button in row.findChildren(QToolButton):
        if button.text() == text:
            return button.isEnabled()
    raise AssertionError(f"Button not found: {text}")


def test_unmanaged_tray_row_stop_button_follows_can_stop():
    app()
    item = ManagedItem(name="Tray", path="", item_type="TRAY_VISIBLE", managed=False)

    disabled = ProcessRow(ProcessState(item=item, status="RUNNING", pid=None, can_stop=False))
    enabled = ProcessRow(ProcessState(item=item, status="RUNNING", pid=123, can_stop=True))

    assert button_enabled(disabled, "STOP") is False
    assert button_enabled(enabled, "STOP") is True
    assert button_enabled(enabled, "START") is False
    assert button_enabled(enabled, "RESTART") is False

