from __future__ import annotations

import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import win32con
import win32gui
from PySide6.QtCore import QFileInfo, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QSystemTrayIcon,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, ConfigStore
from .qdir_ahk_manager import PROJECTS_ROOT, QdirAhkCreateError, QdirAhkManager, QdirAhkScript, QdirAhkState
from .single_instance import SingleInstanceGuard, WM_APP_RESTORE_INSTANCE


TRAY_ICON_ENV_VAR = "EXE_BUILDER_TRAY_ICON_PATH"
TRAY_ICON_BUNDLE_NAME = "_exe_builder_tray_icon.ico"
LOCAL_ICON_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "Icon" / "Tray Icon.ico",
)


class MutuallyExclusiveAhkSurface(QWidget):
    def __init__(self, config: AppConfig, store: ConfigStore, manager: QdirAhkManager) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.manager = manager
        self.states: list[QdirAhkState] = []
        self.busy = False
        self.rows_by_path: dict[str, QdirAhkRow] = {}
        self.empty_label: QLabel | None = None

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Mutually Exclusive AHK Manager")
        title.setObjectName("surfaceTitle")
        header.addWidget(title)
        header.addStretch()
        button_stack = QVBoxLayout()
        button_stack.setSpacing(6)
        config_button = QPushButton("OPEN CONFIG LOCATION")
        config_button.clicked.connect(self.open_config_location)
        button_stack.addWidget(config_button)
        qdir_button = QPushButton("PICK DIRECTORY")
        qdir_button.clicked.connect(self.choose_qdir)
        button_stack.addWidget(qdir_button)
        add_file_button = QPushButton("ADD NEW FILE")
        add_file_button.clicked.connect(self.add_project_launcher)
        button_stack.addWidget(add_file_button)
        header.addLayout(button_stack)
        layout.addLayout(header)

        self.path_label = QLabel(self.config.ahk_qdir_path)
        self.path_label.setObjectName("pathLabel")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.list_layout = QVBoxLayout(self.content)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.refresh()

    def open_config_location(self) -> None:
        try:
            save_and_open_config_location(self.config, self.store)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Open Config Location",
                f"Could not open config location:\n{self.store.path.parent}\n\n{exc}",
            )

    def choose_qdir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select AHK QDIR", self.config.ahk_qdir_path)
        if not selected:
            return
        self.config.ahk_qdir_path = selected
        self.store.save(self.config)
        self._clear_list()
        self.rows_by_path.clear()
        self.refresh()

    def add_project_launcher(self) -> None:
        start_dir = PROJECTS_ROOT if PROJECTS_ROOT.exists() else Path.home()
        selected = QFileDialog.getExistingDirectory(self, "Select Project", str(start_dir))
        if not selected:
            return
        try:
            self.manager.create_project_launcher(selected, self.config.ahk_qdir_path)
        except QdirAhkCreateError as exc:
            QMessageBox.warning(self, "Add New File", str(exc))
            return
        self.refresh()

    def refresh(self) -> None:
        self.path_label.setText(self.config.ahk_qdir_path)
        self.states = self.manager.states(self.config.ahk_qdir_path)
        if not self.states:
            self._remove_missing_rows(set())
            self._show_empty_state()
            return

        self._hide_empty_state()
        row_width = self._row_width()
        active_keys: set[str] = set()
        for index, state in enumerate(self.states):
            key = self.manager.normalize_path(state.script.path)
            active_keys.add(key)
            row = self.rows_by_path.get(key)
            if row is None:
                row = QdirAhkRow(state, actions_enabled=not self.busy, row_width=row_width)
                row.start_requested.connect(lambda current_key=key: self.start(self.rows_by_path[current_key].script))
                row.stop_requested.connect(lambda current_key=key: self.stop(self.rows_by_path[current_key].script))
                self.rows_by_path[key] = row
            else:
                row.update_state(state, actions_enabled=not self.busy, row_width=row_width)
            current_index = self.list_layout.indexOf(row)
            if current_index != index:
                if current_index != -1:
                    self.list_layout.removeWidget(row)
                self.list_layout.insertWidget(index, row)
        self._remove_missing_rows(active_keys)

    def start(self, script: QdirAhkScript) -> None:
        self._run_guarded_action(lambda: self.manager.start(script, self.config.ahk_qdir_path))

    def stop(self, script: QdirAhkScript) -> None:
        self._run_guarded_action(lambda: self.manager.stop(script))

    def _run_guarded_action(self, action) -> None:
        if self.busy:
            return
        self.busy = True
        self.refresh()
        QTimer.singleShot(0, lambda: self._finish_guarded_action(action))

    def _finish_guarded_action(self, action) -> None:
        try:
            action()
        finally:
            self.busy = False
            self.refresh()

    def _clear_list(self) -> None:
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.empty_label = None

    def _row_width(self) -> int:
        margins = self.list_layout.contentsMargins()
        viewport_width = self.scroll.viewport().width()
        if viewport_width < 600:
            viewport_width = 720
        return max(620, viewport_width - margins.left() - margins.right() - 2)

    def _remove_missing_rows(self, active_keys: set[str]) -> None:
        for key in list(self.rows_by_path):
            if key in active_keys:
                continue
            row = self.rows_by_path.pop(key)
            self.list_layout.removeWidget(row)
            row.deleteLater()

    def _show_empty_state(self) -> None:
        if self.empty_label is not None:
            return
        self.empty_label = QLabel("No .ahk files found in QDIR")
        self.empty_label.setObjectName("emptyState")
        self.list_layout.addWidget(self.empty_label)

    def _hide_empty_state(self) -> None:
        if self.empty_label is None:
            return
        self.list_layout.removeWidget(self.empty_label)
        self.empty_label.deleteLater()
        self.empty_label = None


class QdirAhkRow(QFrame):
    from PySide6.QtCore import Signal

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, state: QdirAhkState, actions_enabled: bool = True, row_width: int = 720) -> None:
        super().__init__()
        self.script = state.script
        self.setObjectName("processRow")
        self.setFixedWidth(row_width)
        self.setFixedHeight(52)
        self.setMinimumHeight(52)
        self.setMaximumHeight(52)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.icon = QLabel()
        self.icon.setPixmap(icon_for_path(state.script.path).pixmap(24, 24))
        self.icon.setFixedSize(24, 24)
        layout.addWidget(self.icon)

        self.name = QLabel(state.script.name)
        self.name.setFixedWidth(330)
        layout.addWidget(self.name)

        self.status = QLabel(state.status)
        self.status.setObjectName(status_label_name(state.status))
        self.status.setFixedWidth(76)
        self.status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.status)

        layout.addStretch()
        self.start = QToolButton()
        self.start.setObjectName("qdirActionButton")
        self.start.setText("START")
        self.start.setFixedSize(68, 34)
        self.start.pressed.connect(lambda button=self.start: self._emit_once(button, self.start_requested.emit))
        layout.addWidget(self.start)

        self.stop = QToolButton()
        self.stop.setObjectName("qdirActionButton")
        self.stop.setText("STOP")
        self.stop.setFixedSize(68, 34)
        self.stop.pressed.connect(lambda button=self.stop: self._emit_once(button, self.stop_requested.emit))
        layout.addWidget(self.stop)
        self.update_state(state, actions_enabled, row_width)

    def _emit_once(self, button: QToolButton, emit) -> None:
        button.setEnabled(False)
        emit()

    def update_state(self, state: QdirAhkState, actions_enabled: bool = True, row_width: int = 720) -> None:
        self.script = state.script
        self.setFixedWidth(row_width)
        self.name.setText(state.script.name)
        self.status.setText(state.status)
        self.status.setObjectName(status_label_name(state.status))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.start.setEnabled(actions_enabled and state.status != "RUNNING")
        self.stop.setEnabled(actions_enabled and state.status == "RUNNING")


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self.store = store
        self.config = store.load()
        self.qdir_ahk_manager = QdirAhkManager()
        self.close_to_tray = False
        self.exit_requested = False

        self.setWindowTitle("Tray Manager")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.MSWindowsFixedSizeDialogHint
        )
        self.setFixedSize(775, 590)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.qdir_ahk_surface = MutuallyExclusiveAhkSurface(self.config, self.store, self.qdir_ahk_manager)
        layout.addWidget(self.qdir_ahk_surface)
        self.setCentralWidget(central)

        self.qdir_timer = QTimer(self)
        self.qdir_timer.timeout.connect(self.refresh_qdir_surface)
        self.qdir_timer.start(self.config.refresh_interval_ms)

        self._apply_style()

    def closeEvent(self, event) -> None:
        self.store.save(self.config)
        if self.close_to_tray and not self.exit_requested:
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)

    def enable_close_to_tray(self) -> None:
        self.close_to_tray = True

    def request_exit(self) -> None:
        self.exit_requested = True
        self.store.save(self.config)

    def refresh_qdir_surface(self) -> None:
        if self.qdir_ahk_surface.busy:
            return
        self.qdir_ahk_surface.refresh()

    def nativeEvent(self, event_type, message):
        try:
            event_name = bytes(event_type).decode(errors="ignore")
        except Exception:
            event_name = str(event_type)

        if event_name == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_APP_RESTORE_INSTANCE:
                QTimer.singleShot(0, self.restore_from_activation)
                return True, 0

        return False, 0

    def restore_from_activation(self) -> None:
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.repaint()
        self.update()
        try:
            hwnd = int(self.winId())
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f4f5f7; }
            QWidget { font-family: Segoe UI; font-size: 10pt; color: #202124; }
            #surfaceTitle { font-weight: 700; letter-spacing: 0; }
            #emptyState { color: #667085; padding: 28px; }
            #processRow {
                background: #ffffff;
                border: 1px solid #d6dae1;
                border-radius: 8px;
            }
            #stateLabel { color: #667085; font-size: 8pt; font-weight: 700; }
            #running { color: #0b7a3b; font-weight: 700; }
            #stopped { color: #8a1f11; font-weight: 700; }
            #failed { color: #b42318; font-weight: 700; }
            #pathLabel { color: #667085; }
            QPushButton, QToolButton {
                background: #ffffff;
                border: 1px solid #c8ced8;
                border-radius: 6px;
                padding: 6px 10px;
            }
            #qdirActionButton {
                min-width: 68px;
                max-width: 68px;
                min-height: 34px;
                max-height: 34px;
                padding: 0;
                border: 1px solid #c8ced8;
            }
            #qdirActionButton:disabled {
                background: #f3f4f6;
                border: 1px solid #c8ced8;
                color: #98a2b3;
                padding: 0;
            }
            QPushButton:hover, QToolButton:hover { background: #edf2f7; }
            #dangerButton { border-color: #b42318; color: #b42318; }
            QScrollArea { border: none; background: transparent; }
            """
        )


class ApplicationTrayIcon:
    def __init__(self, app: QApplication, window: MainWindow, icon: QIcon) -> None:
        self.app = app
        self.window = window
        self.tray_icon = QSystemTrayIcon(window)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Tray Manager")

        self.menu = QMenu(window)
        self.open_action = QAction("Open Tray Manager", window)
        self.hide_action = QAction("Hide", window)
        self.exit_action = QAction("Exit", window)

        self.open_action.triggered.connect(self.show_window)
        self.hide_action.triggered.connect(window.hide)
        self.exit_action.triggered.connect(self.exit_app)

        self.menu.addAction(self.open_action)
        self.menu.addAction(self.hide_action)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._activated)

    def show(self) -> None:
        self.tray_icon.show()

    def toggle_window(self) -> None:
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.show_window()

    def show_window(self) -> None:
        self.window.restore_from_activation()

    def exit_app(self) -> None:
        self.window.request_exit()
        self.tray_icon.hide()
        self.app.quit()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()


def application_icon(window=None) -> QIcon:
    icon_path = application_icon_path(window)
    if icon_path is not None:
        return QIcon(str(icon_path))

    if window is not None and hasattr(window, "windowIcon"):
        icon = window.windowIcon()
        if not icon.isNull():
            return icon

    themed_icon = QIcon.fromTheme("applications-system")
    if not themed_icon.isNull():
        return themed_icon
    return QApplication.style().standardIcon(QStyle.SP_ComputerIcon)


def application_icon_path(window=None) -> Path | None:
    for candidate in application_icon_candidates(window):
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return candidate
    return None


def application_icon_candidates(window=None) -> list[Path]:
    candidates: list[Path] = []

    env_icon = os.environ.get(TRAY_ICON_ENV_VAR, "").strip()
    if env_icon:
        candidates.append(Path(env_icon))

    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        candidates.extend(_expanded_bundle_icon_candidates(Path(bundle_dir)))

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        _expanded_bundle_icon_candidates(executable_dir)
        + _expanded_bundle_icon_candidates(executable_dir / "_internal")
    )

    candidates.extend(LOCAL_ICON_CANDIDATES)
    return _dedupe_icon_candidates(candidates)


def _expanded_bundle_icon_candidates(base_dir: Path) -> list[Path]:
    bundle_path = base_dir / TRAY_ICON_BUNDLE_NAME
    candidates = [bundle_path]
    if bundle_path.is_dir():
        candidates.extend(sorted(bundle_path.glob("*.ico")))
    return candidates


def _dedupe_icon_candidates(candidates: list[Path]) -> list[Path]:
    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(candidate)
    return unique_candidates


def configure_tray_application(app: QApplication, window: MainWindow) -> ApplicationTrayIcon | None:
    app.setQuitOnLastWindowClosed(False)
    icon = application_icon(window)
    app.setWindowIcon(icon)
    window.setWindowIcon(icon)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(True)
        window.show()
        return None

    window.enable_close_to_tray()
    tray_icon = ApplicationTrayIcon(app, window, icon)
    window.application_tray_icon = tray_icon
    tray_icon.show()
    return tray_icon


def icon_for_path(path: str) -> QIcon:
    file_path = Path(path)
    if file_path.exists():
        provider = QFileIconProvider()
        return provider.icon(QFileInfo(str(file_path)))
    return QApplication.style().standardIcon(QStyle.SP_FileIcon)


def status_label_name(status: str) -> str:
    return {
        "RUNNING": "running",
        "FAILED": "failed",
    }.get(status, "stopped")


def open_folder_in_explorer(path: Path) -> None:
    subprocess.run(["explorer", str(path)])


def save_and_open_config_location(config: AppConfig, store: ConfigStore) -> None:
    store.save(config)
    open_folder_in_explorer(store.path.parent)


def run() -> int:
    guard = SingleInstanceGuard()
    if not guard.acquire():
        return 0

    try:
        app = QApplication([])
        window = MainWindow(ConfigStore())
        configure_tray_application(app, window)
        return app.exec()
    finally:
        guard.release()
