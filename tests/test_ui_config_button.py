from pathlib import Path
from subprocess import CompletedProcess

from PySide6.QtWidgets import QApplication

import ahk_workspace_manager.ui as ui_module
from ahk_workspace_manager.config import AppConfig
from ahk_workspace_manager.qdir_ahk_manager import QdirAhkManager, QdirAhkScript, QdirAhkState
from ahk_workspace_manager.ui import MutuallyExclusiveAhkSurface
from ahk_workspace_manager.ui import open_folder_in_explorer, save_and_open_config_location


class FakeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.saved_config = None

    def save(self, config: AppConfig) -> None:
        self.saved_config = config


class FakeQdirAhkManager:
    def __init__(self, start_result: bool = True, stop_result: bool = True) -> None:
        self.script = QdirAhkScript(name="Tool.ahk", path="C:/Tool/Tool.ahk")
        self.start_result = start_result
        self.stop_result = stop_result
        self.started = []
        self.stopped = []

    def states(self, directory: str):
        return [QdirAhkState(script=self.script, status="STOPPED")]

    def normalize_path(self, path: str) -> str:
        return path.casefold()

    def start(self, script: QdirAhkScript, directory: str) -> bool:
        self.started.append((script, directory))
        return self.start_result

    def stop(self, script: QdirAhkScript) -> bool:
        self.stopped.append(script)
        return self.stop_result


def run_guarded_actions_immediately(monkeypatch) -> None:
    monkeypatch.setattr(ui_module.QTimer, "singleShot", lambda _interval, callback: callback())


def test_open_folder_in_explorer_opens_folder(monkeypatch, tmp_path):
    calls = []
    config_dir = tmp_path / "AHKQuickLaunchManager"
    monkeypatch.setattr(ui_module.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    open_folder_in_explorer(config_dir)

    assert calls == [((["explorer", str(config_dir)],), {})]
    command = calls[0][0][0]
    assert "/select" not in command
    assert "workspace_manager.json" not in command
    assert calls[0][1].get("check") is not True


def test_open_folder_in_explorer_ignores_explorer_return_code(monkeypatch, tmp_path):
    config_dir = tmp_path / "AHKQuickLaunchManager"
    monkeypatch.setattr(
        ui_module.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args=args, returncode=1),
    )

    open_folder_in_explorer(config_dir)


def test_save_and_open_config_location_saves_before_opening(monkeypatch, tmp_path):
    opened_paths = []
    config = AppConfig(ahk_qdir_path=str(tmp_path / "qdir"))
    store = FakeStore(tmp_path / "AHKQuickLaunchManager" / "workspace_manager.json")
    monkeypatch.setattr(ui_module, "open_folder_in_explorer", lambda path: opened_paths.append(path))

    save_and_open_config_location(config, store)

    assert store.saved_config is config
    assert opened_paths == [store.path.parent]
    assert store.path not in opened_paths


def test_open_qdir_location_opens_configured_qdir(monkeypatch, tmp_path):
    opened_paths = []
    qdir = tmp_path / "qdir"
    config = AppConfig(ahk_qdir_path=str(qdir))
    store = FakeStore(tmp_path / "AHKQuickLaunchManager" / "workspace_manager.json")
    monkeypatch.setattr(ui_module, "open_folder_in_explorer", lambda path: opened_paths.append(path))

    app = QApplication.instance() or QApplication([])
    surface = MutuallyExclusiveAhkSurface(config, store, QdirAhkManager())
    surface.open_qdir_location()

    assert app is not None
    assert opened_paths == [qdir]


def test_start_success_calls_start_success_callback(monkeypatch, tmp_path):
    run_guarded_actions_immediately(monkeypatch)
    hidden = []
    config = AppConfig(ahk_qdir_path=str(tmp_path / "qdir"))
    store = FakeStore(tmp_path / "AHKQuickLaunchManager" / "workspace_manager.json")
    manager = FakeQdirAhkManager(start_result=True)

    app = QApplication.instance() or QApplication([])
    surface = MutuallyExclusiveAhkSurface(config, store, manager, on_start_success=lambda: hidden.append(True))
    surface.start(manager.script)

    assert app is not None
    assert manager.started == [(manager.script, config.ahk_qdir_path)]
    assert hidden == [True]


def test_start_failure_does_not_call_start_success_callback(monkeypatch, tmp_path):
    run_guarded_actions_immediately(monkeypatch)
    hidden = []
    config = AppConfig(ahk_qdir_path=str(tmp_path / "qdir"))
    store = FakeStore(tmp_path / "AHKQuickLaunchManager" / "workspace_manager.json")
    manager = FakeQdirAhkManager(start_result=False)

    app = QApplication.instance() or QApplication([])
    surface = MutuallyExclusiveAhkSurface(config, store, manager, on_start_success=lambda: hidden.append(True))
    surface.start(manager.script)

    assert app is not None
    assert manager.started == [(manager.script, config.ahk_qdir_path)]
    assert hidden == []


def test_stop_does_not_call_start_success_callback(monkeypatch, tmp_path):
    run_guarded_actions_immediately(monkeypatch)
    hidden = []
    config = AppConfig(ahk_qdir_path=str(tmp_path / "qdir"))
    store = FakeStore(tmp_path / "AHKQuickLaunchManager" / "workspace_manager.json")
    manager = FakeQdirAhkManager(stop_result=True)

    app = QApplication.instance() or QApplication([])
    surface = MutuallyExclusiveAhkSurface(config, store, manager, on_start_success=lambda: hidden.append(True))
    surface.stop(manager.script)

    assert app is not None
    assert manager.stopped == [manager.script]
    assert hidden == []
