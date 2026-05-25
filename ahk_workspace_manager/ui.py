from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QFileInfo, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .ahk_manager import AHKManager
from .config import AppConfig, ConfigStore, ManagedItem, TaskbarItem
from .process_manager import ProcessManager, ProcessState
from .taskbar_manager import TaskbarManager


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


class TaskbarSurface(DropSurface):
    def __init__(self, config: AppConfig, store: ConfigStore, manager: TaskbarManager) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.manager = manager
        self.selected_path: str | None = None

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("TASKBAR SURFACE")
        title.setObjectName("surfaceTitle")
        header.addWidget(title)
        header.addStretch()
        self.pin_button = QPushButton("Pin")
        self.pin_button.setEnabled(False)
        self.pin_button.clicked.connect(self.pin_selected)
        header.addWidget(self.pin_button)
        for label, callback in (
            ("Pin All", self.pin_all),
            ("Unpin All", self.unpin_all),
            ("Remove All", self.remove_all),
            ("Refresh", self.refresh),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            header.addWidget(button)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.refresh()

    def dropEvent(self, event: QDropEvent) -> None:
        for path in self.dropped_paths(event):
            self.manager.add_path(path)
        self.store.save(self.config)
        self.refresh()
        super().dropEvent(event)

    def refresh(self) -> None:
        self._clear_grid()
        if self._selected_item() is None:
            self.selected_path = None
        self._sync_pin_button()
        if not self.config.taskbar_items:
            label = QLabel("Drop .exe, shortcuts, or folders here")
            label.setObjectName("emptyState")
            self.grid.addWidget(label, 0, 0)
            return

        for index, item in enumerate(self.config.taskbar_items):
            selected = item.path == self.selected_path
            tile = TaskbarTile(item, selected=selected)
            tile.selected_requested.connect(lambda checked=False, current=item: self.select_item(current))
            tile.launch_requested.connect(lambda checked=False, current=item: self.launch(current))
            tile.unpin_requested.connect(lambda checked=False, current=item: self.unpin(current))
            tile.remove_requested.connect(lambda checked=False, current=item: self.remove(current))
            row, column = divmod(index, 4)
            self.grid.addWidget(tile, row, column)

    def select_item(self, item: TaskbarItem) -> None:
        self.selected_path = item.path
        self.refresh()

    def pin_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        item.pinned = self.manager.pin(item.path)
        self.store.save(self.config)
        self.refresh()

    def pin_all(self) -> None:
        self.manager.pin_all()
        self.store.save(self.config)
        self.refresh()

    def unpin_all(self) -> None:
        self.manager.unpin_all()
        self.store.save(self.config)
        self.refresh()

    def remove_all(self) -> None:
        self.manager.remove_all()
        self.selected_path = None
        self.store.save(self.config)
        self.refresh()

    def launch(self, item: TaskbarItem) -> None:
        path = Path(item.path)
        if path.exists():
            if path.suffix.lower() == ".lnk":
                os.startfile(str(path))
            else:
                subprocess.Popen([str(path)], cwd=str(path.parent))

    def unpin(self, item: TaskbarItem) -> None:
        item.pinned = not self.manager.unpin(item.path)
        self.store.save(self.config)
        self.refresh()

    def remove(self, item: TaskbarItem) -> None:
        self.manager.remove(item)
        if self.selected_path == item.path:
            self.selected_path = None
        self.store.save(self.config)
        self.refresh()

    def _selected_item(self) -> TaskbarItem | None:
        for item in self.config.taskbar_items:
            if item.path == self.selected_path:
                return item
        return None

    def _sync_pin_button(self) -> None:
        self.pin_button.setEnabled(self._selected_item() is not None)

    def _clear_grid(self) -> None:
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class TaskbarTile(QFrame):
    selected_requested = Signal()
    launch_requested = Signal()
    unpin_requested = Signal()
    remove_requested = Signal()

    def __init__(self, item: TaskbarItem, selected: bool = False) -> None:
        super().__init__()
        self.item = item
        self.setObjectName("tile")
        self.setProperty("selected", selected)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)
        self.setFixedSize(150, 132)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        remove_row = QHBoxLayout()
        remove_row.addStretch()
        remove_button = QToolButton()
        remove_button.setText("X")
        remove_button.setObjectName("tileRemoveButton")
        remove_button.setFixedSize(22, 22)
        remove_button.clicked.connect(self.remove_requested.emit)
        remove_row.addWidget(remove_button)
        layout.addLayout(remove_row)

        icon = QLabel()
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(icon_for_path(item.path).pixmap(32, 32))
        layout.addWidget(icon)

        name = QLabel(item.name)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)

        state = QLabel("PINNED" if item.pinned else "UNVERIFIED")
        state.setObjectName("stateLabel")
        state.setAlignment(Qt.AlignCenter)
        layout.addWidget(state)

    def mousePressEvent(self, event) -> None:
        self.selected_requested.emit()
        super().mousePressEvent(event)

    def open_menu(self, pos) -> None:
        menu = QMenu(self)
        launch = menu.addAction("Launch")
        unpin = menu.addAction("Unpin")
        open_location = menu.addAction("Open File Location")
        remove = menu.addAction("Remove From Surface")
        action = menu.exec(self.mapToGlobal(pos))
        if action == launch:
            self.launch_requested.emit()
        elif action == unpin:
            self.unpin_requested.emit()
        elif action == open_location:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.item.path).parent)))
        elif action == remove:
            self.remove_requested.emit()


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


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self.store = store
        self.config = store.load()
        self.taskbar_manager = TaskbarManager(self.config)
        self.process_manager = ProcessManager(self.config)
        self.ahk_manager = AHKManager(self.config, self.process_manager)

        self.setWindowTitle("AHK Workspace Manager")
        self.resize(860, 720)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(TaskbarSurface(self.config, self.store, self.taskbar_manager))
        self.tray_surface = TraySurface(self.config, self.store, self.process_manager, self.ahk_manager)
        splitter.addWidget(self.tray_surface)
        splitter.setSizes([280, 440])
        self.setCentralWidget(splitter)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tray_surface.refresh)
        self.timer.start(self.config.refresh_interval_ms)

        self._apply_style()

    def closeEvent(self, event) -> None:
        self.store.save(self.config)
        super().closeEvent(event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f4f5f7; }
            QWidget { font-family: Segoe UI; font-size: 10pt; color: #202124; }
            #surfaceTitle { font-weight: 700; letter-spacing: 0; }
            #emptyState { color: #667085; padding: 28px; }
            #tile, #processRow {
                background: #ffffff;
                border: 1px solid #d6dae1;
                border-radius: 8px;
            }
            #tile[selected="true"] {
                background: #eaf3ff;
                border: 2px solid #1b66d2;
            }
            #tileRemoveButton {
                padding: 0;
                font-weight: 700;
                color: #6b7280;
            }
            #tileRemoveButton:hover {
                background: #fee4e2;
                border-color: #d92d20;
                color: #b42318;
            }
            #stateLabel { color: #667085; font-size: 8pt; font-weight: 700; }
            #running { color: #0b7a3b; font-weight: 700; }
            #stopped { color: #8a1f11; font-weight: 700; }
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


def run() -> int:
    app = QApplication([])
    window = MainWindow(ConfigStore())
    window.show()
    return app.exec()
