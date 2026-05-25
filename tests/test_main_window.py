from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ahk_workspace_manager.config import ConfigStore
from ahk_workspace_manager.ui import MainWindow


def app():
    existing = QApplication.instance()
    return existing or QApplication([])


def test_main_window_is_fixed_size_without_maximize_button(tmp_path):
    app()
    window = MainWindow(ConfigStore(tmp_path / "config.json"))

    assert window.width() == 775
    assert window.height() == 1000
    assert window.minimumWidth() == 775
    assert window.maximumWidth() == 775
    assert window.minimumHeight() == 1000
    assert window.maximumHeight() == 1000
    assert not window.windowFlags() & Qt.WindowMaximizeButtonHint

