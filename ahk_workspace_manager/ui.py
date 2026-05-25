from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, QTimer, Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
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

from .ahk_manager import AHKManager
from .config import AppConfig, ConfigStore, ManagedItem
from .process_manager import ProcessManager, ProcessState
from .qdir_ahk_manager import QdirAhkManager, QdirAhkScript, QdirAhkState
from .single_instance import SingleInstanceGuard


class DropSurface(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        event.acceptProposedAction()

    def dropped_paths(self, event: QDropEvent) -> list[str]:
        return [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]


class TraySurface(DropSurface):
    def __init__(
        self,
        config: AppConfig,
        store: ConfigStore,
        process_manager: ProcessManager,
        ahk_manager: AHKManager,
    ) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.process_manager = process_manager
        self.ahk_manager = ahk_manager
        self.states: list[ProcessState] = []

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("TRAY SURFACE")
        title.setObjectName("surfaceTitle")
        header.addWidget(title)
        header.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        kill_all = QPushButton("Kill All")
        kill_all.setObjectName("dangerButton")
        kill_all.clicked.connect(self.kill_all)
        header.addWidget(refresh)
        header.addWidget(kill_all)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.list_layout = QVBoxLayout(self.content)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.refresh()

    def dropEvent(self, event: QDropEvent) -> None:
        group = None
        paths = self.dropped_paths(event)
        if any(path.lower().endswith(".ahk") or Path(path).is_dir() for path in paths):
            group, ok = QInputDialog.getText(self, "AHK Group", "Exclusive group name (optional):")
            group = optional_group_name(group, ok)

        for path in paths:
            added = self.process_manager.register_path(path, group=group)
            for item in added:
                if item.item_type == "AHK":
                    self.ahk_manager.set_group(item, group)
        self.store.save(self.config)
        self.refresh()
        super().dropEvent(event)

    def refresh(self) -> None:
        self.states = self.process_manager.poll()
        self._clear_list()
        if not self.states:
            label = QLabel("Drop .ahk, .exe, or folders here")
            label.setObjectName("emptyState")
            self.list_layout.addWidget(label)
            return

        for state in self.states:
            row = ProcessRow(state)
            row.start_requested.connect(lambda checked=False, current=state.item: self.start(current))
            row.stop_requested.connect(lambda checked=False, current=state.item: self.stop(current))
            row.restart_requested.connect(lambda checked=False, current=state.item: self.restart(current))
            self.list_layout.addWidget(row)

    def start(self, item: ManagedItem) -> None:
        if item.item_type == "AHK":
            self.ahk_manager.start(item)
        else:
            self.process_manager.launch(item)
        self.store.save(self.config)
        self.refresh()

    def stop(self, item: ManagedItem) -> None:
        self.process_manager.terminate(item)
        self.store.save(self.config)
        self.refresh()

    def restart(self, item: ManagedItem) -> None:
        if item.item_type == "AHK":
            self.process_manager.terminate(item)
            self.ahk_manager.start(item)
        else:
            self.process_manager.restart(item)
        self.store.save(self.config)
        self.refresh()

    def kill_all(self) -> None:
        killed = self.process_manager.kill_all_managed()
        QMessageBox.information(self, "Kill All", f"Terminated {killed} managed process(es).")
        self.refresh()

    def _clear_list(self) -> None:
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class ProcessRow(QFrame):
    from PySide6.QtCore import Signal

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()

    def __init__(self, state: ProcessState) -> None:
        super().__init__()
        self.setObjectName("processRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        icon = QLabel()
        icon.setPixmap(icon_for_path(state.item.path).pixmap(24, 24))
        layout.addWidget(icon)

        name = QLabel(state.item.name)
        name.setMinimumWidth(180)
        layout.addWidget(name)

        status = QLabel(state.status)
        status.setObjectName("running" if state.status == "RUNNING" else "stopped")
        layout.addWidget(status)

        item_type = QLabel(state.item.group or state.item.item_type)
        item_type.setMinimumWidth(120)
        layout.addWidget(item_type)

        layout.addStretch()
        for text, signal, enabled in (
            ("START", self.start_requested, state.item.managed),
            ("STOP", self.stop_requested, state.can_stop),
            ("RESTART", self.restart_requested, state.item.managed),
        ):
            button = QToolButton()
            button.setText(text)
            button.setEnabled(enabled)
            button.clicked.connect(signal.emit)
            layout.addWidget(button)


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
        qdir_button = QPushButton("QDIR")
        qdir_button.clicked.connect(self.choose_qdir)
        header.addWidget(qdir_button)
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

    def choose_qdir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select AHK QDIR", self.config.ahk_qdir_path)
        if not selected:
            return
        self.config.ahk_qdir_path = selected
        self.store.save(self.config)
        self._clear_list()
        self.rows_by_path.clear()
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
        self.process_manager = ProcessManager(self.config)
        self.ahk_manager = AHKManager(self.config, self.process_manager)
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
        self.setFixedSize(775, 1000)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.tray_surface = TraySurface(self.config, self.store, self.process_manager, self.ahk_manager)
        self.qdir_ahk_surface = MutuallyExclusiveAhkSurface(self.config, self.store, self.qdir_ahk_manager)
        layout.addWidget(self.tray_surface, 2)
        layout.addWidget(self.qdir_ahk_surface, 1)
        self.setCentralWidget(central)

        self.tray_timer = QTimer(self)
        self.tray_timer.timeout.connect(self.refresh_tray_surface)
        self.tray_timer.start(self.config.refresh_interval_ms)

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

    def refresh_tray_surface(self) -> None:
        if self.qdir_ahk_surface.busy:
            return
        self.tray_surface.refresh()

    def refresh_qdir_surface(self) -> None:
        if self.qdir_ahk_surface.busy:
            return
        self.qdir_ahk_surface.refresh()

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
        self.tray_icon = QSystemTrayIcon(icon, window)
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

    def show_window(self) -> None:
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def exit_app(self) -> None:
        self.window.request_exit()
        self.tray_icon.hide()
        self.app.quit()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()


def application_icon() -> QIcon:
    return QApplication.style().standardIcon(QStyle.SP_ComputerIcon)


def configure_tray_application(app: QApplication, window: MainWindow) -> ApplicationTrayIcon | None:
    app.setQuitOnLastWindowClosed(False)
    icon = application_icon()
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


def optional_group_name(group: str | None, ok: bool) -> str | None:
    if not ok or group is None:
        return None
    return group.strip() or None


def status_label_name(status: str) -> str:
    return {
        "RUNNING": "running",
        "FAILED": "failed",
    }.get(status, "stopped")


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
