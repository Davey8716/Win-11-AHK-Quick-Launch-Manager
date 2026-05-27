from pathlib import Path
from subprocess import CompletedProcess

import ahk_workspace_manager.ui as ui_module
from ahk_workspace_manager.config import AppConfig
from ahk_workspace_manager.ui import open_folder_in_explorer, save_and_open_config_location


class FakeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.saved_config = None

    def save(self, config: AppConfig) -> None:
        self.saved_config = config


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
