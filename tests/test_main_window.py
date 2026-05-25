from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ahk_workspace_manager import ui
from ahk_workspace_manager.config import ConfigStore
from ahk_workspace_manager.ui import MainWindow


def app():
    existing = QApplication.instance()
    current = existing or QApplication([])
    current.setQuitOnLastWindowClosed(True)
    return current


def test_main_window_is_fixed_size(tmp_path):
    app()
    window = MainWindow(ConfigStore(tmp_path / "config.json"))

    assert window.width() == 775
    assert window.height() == 1000
    assert window.minimumWidth() == 775
    assert window.maximumWidth() == 775
    assert window.minimumHeight() == 1000
    assert window.maximumHeight() == 1000
    assert window.windowFlags() & Qt.WindowSystemMenuHint
    assert window.windowFlags() & Qt.WindowMinimizeButtonHint
    assert window.windowFlags() & Qt.WindowCloseButtonHint
    assert window.windowFlags() & Qt.MSWindowsFixedSizeDialogHint
    assert not window.windowFlags() & Qt.WindowMaximizeButtonHint


def test_close_hides_window_when_tray_mode_is_enabled(tmp_path):
    app()
    window = MainWindow(ConfigStore(tmp_path / "config.json"))
    window.enable_close_to_tray()
    window.show()

    assert window.isVisible()
    assert not window.close()
    assert not window.isVisible()


def test_requested_exit_allows_window_to_close(tmp_path):
    app()
    config_path = tmp_path / "config.json"
    window = MainWindow(ConfigStore(config_path))
    window.enable_close_to_tray()
    window.config.refresh_interval_ms = 2345
    window.show()

    window.request_exit()

    assert window.close()
    assert '"refresh_interval_ms": 2345' in config_path.read_text(encoding="utf-8")


def test_configure_tray_application_starts_hidden_when_tray_is_available(tmp_path, monkeypatch):
    qt_app = app()
    window = MainWindow(ConfigStore(tmp_path / "config.json"))
    monkeypatch.setattr(ui.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))

    class FakeTrayIcon:
        def __init__(self, app, window, icon):
            self.app = app
            self.window = window
            self.icon = icon
            self.shown = False

        def show(self):
            self.shown = True

    monkeypatch.setattr(ui, "ApplicationTrayIcon", FakeTrayIcon)

    tray_icon = ui.configure_tray_application(qt_app, window)

    assert tray_icon.shown
    assert window.close_to_tray
    assert not window.isVisible()
    assert not qt_app.quitOnLastWindowClosed()
    assert window.application_tray_icon is tray_icon


def test_configure_tray_application_shows_window_when_tray_is_unavailable(tmp_path, monkeypatch):
    qt_app = app()
    window = MainWindow(ConfigStore(tmp_path / "config.json"))
    monkeypatch.setattr(ui.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))

    tray_icon = ui.configure_tray_application(qt_app, window)

    assert tray_icon is None
    assert not window.close_to_tray
    assert window.isVisible()
    assert qt_app.quitOnLastWindowClosed()


def test_single_clicking_tray_icon_opens_window(monkeypatch):
    class FakeWindow:
        def __init__(self):
            self.shown = False
            self.raised = False
            self.activated = False

        def isMinimized(self):
            return False

        def show(self):
            self.shown = True

        def showNormal(self):
            raise AssertionError("showNormal should not be used for a hidden, non-minimized window")

        def raise_(self):
            self.raised = True

        def activateWindow(self):
            self.activated = True

    tray_icon = ui.ApplicationTrayIcon.__new__(ui.ApplicationTrayIcon)
    tray_icon.window = FakeWindow()

    tray_icon._activated(ui.QSystemTrayIcon.Trigger)

    assert tray_icon.window.shown
    assert tray_icon.window.raised
    assert tray_icon.window.activated


def test_show_window_restores_minimized_window_before_focus():
    class FakeWindow:
        def __init__(self):
            self.restored = False
            self.shown = False
            self.raised = False
            self.activated = False

        def isMinimized(self):
            return True

        def show(self):
            self.shown = True

        def showNormal(self):
            self.restored = True

        def raise_(self):
            self.raised = True

        def activateWindow(self):
            self.activated = True

    tray_icon = ui.ApplicationTrayIcon.__new__(ui.ApplicationTrayIcon)
    tray_icon.window = FakeWindow()

    tray_icon.show_window()

    assert tray_icon.window.restored
    assert not tray_icon.window.shown
    assert tray_icon.window.raised
    assert tray_icon.window.activated
