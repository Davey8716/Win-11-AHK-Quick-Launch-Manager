from PySide6.QtWidgets import QApplication, QToolButton

from ahk_workspace_manager.qdir_ahk_manager import QdirAhkScript, QdirAhkState
from ahk_workspace_manager.ui import QdirAhkRow, status_label_name


def app():
    existing = QApplication.instance()
    return existing or QApplication([])


def button_enabled(row: QdirAhkRow, text: str) -> bool:
    for button in row.findChildren(QToolButton):
        if button.text() == text:
            return button.isEnabled()
    raise AssertionError(f"Button not found: {text}")


def test_qdir_row_buttons_follow_running_state():
    app()
    script = QdirAhkScript(name="FPS.ahk", path="C:/Scripts/FPS.ahk")

    stopped = QdirAhkRow(QdirAhkState(script=script, status="STOPPED"))
    running = QdirAhkRow(QdirAhkState(script=script, status="RUNNING", pid=10))

    assert button_enabled(stopped, "START") is True
    assert button_enabled(stopped, "STOP") is False
    assert button_enabled(running, "START") is False
    assert button_enabled(running, "STOP") is True


def test_status_label_name_maps_failed_state():
    assert status_label_name("FAILED") == "failed"
    assert status_label_name("RUNNING") == "running"
    assert status_label_name("STOPPED") == "stopped"

