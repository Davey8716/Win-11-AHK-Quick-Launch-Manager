from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, QTimer, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
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
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .ahk_manager import AHKManager
from .config import AppConfig, ConfigStore, ManagedItem
from .process_manager import ProcessManager, ProcessState
from .qdir_ahk_manager import QdirAhkManager, QdirAhkScript, QdirAhkState


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
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.refresh()

    def choose_qdir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select AHK QDIR", self.config.ahk_qdir_path)
        if not selected:
            return
        self.config.ahk_qdir_path = selected
        self.store.save(self.config)
        self.refresh()

    def refresh(self) -> None:
        self.path_label.setText(self.config.ahk_qdir_path)
        self.states = self.manager.states(self.config.ahk_qdir_path)
        self._clear_list()
        if not self.states:
            label = QLabel("No .ahk files found in QDIR")
            label.setObjectName("emptyState")
            self.list_layout.addWidget(label)
            return

        for state in self.states:
            row = QdirAhkRow(state)
            row.start_requested.connect(lambda checked=False, current=state.script: self.start(current))
            row.stop_requested.connect(lambda checked=False, current=state.script: self.stop(current))
            self.list_layout.addWidget(row)

    def start(self, script: QdirAhkScript) -> None:
        self.manager.start(script, self.config.ahk_qdir_path)
        self.refresh()

    def stop(self, script: QdirAhkScript) -> None:
        self.manager.stop(script)
        self.refresh()

    def _clear_list(self) -> None:
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class QdirAhkRow(QFrame):
    from PySide6.QtCore import Signal

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, state: QdirAhkState) -> None:
        super().__init__()
        self.setObjectName("processRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        icon = QLabel()
        icon.setPixmap(icon_for_path(state.script.path).pixmap(24, 24))
        layout.addWidget(icon)

        name = QLabel(state.script.name)
        name.setMinimumWidth(240)
        layout.addWidget(name)

        status = QLabel(state.status)
        status.setObjectName(status_label_name(state.status))
        layout.addWidget(status)

        layout.addStretch()
        start = QToolButton()
        start.setText("START")
        start.setEnabled(state.status != "RUNNING")
        start.clicked.connect(self.start_requested.emit)
        layout.addWidget(start)

        stop = QToolButton()
        stop.setText("STOP")
        stop.setEnabled(state.status == "RUNNING")
        stop.clicked.connect(self.stop_requested.emit)
        layout.addWidget(stop)


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self.store = store
        self.config = store.load()
        self.process_manager = ProcessManager(self.config)
        self.ahk_manager = AHKManager(self.config, self.process_manager)
        self.qdir_ahk_manager = QdirAhkManager()

        self.setWindowTitle("Tray Manager")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.setFixedSize(775, 1000)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.tray_surface = TraySurface(self.config, self.store, self.process_manager, self.ahk_manager)
        self.qdir_ahk_surface = MutuallyExclusiveAhkSurface(self.config, self.store, self.qdir_ahk_manager)
        layout.addWidget(self.tray_surface, 2)
        layout.addWidget(self.qdir_ahk_surface, 1)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_surfaces)
        self.timer.start(self.config.refresh_interval_ms)

        self._apply_style()

    def closeEvent(self, event) -> None:
        self.store.save(self.config)
        super().closeEvent(event)

    def refresh_surfaces(self) -> None:
        self.tray_surface.refresh()
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
            QPushButton:hover, QToolButton:hover { background: #edf2f7; }
            #dangerButton { border-color: #b42318; color: #b42318; }
            QScrollArea { border: none; background: transparent; }
            """
        )


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
    app = QApplication([])
    window = MainWindow(ConfigStore())
    window.show()
    return app.exec()
