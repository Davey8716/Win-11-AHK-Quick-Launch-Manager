import json
from pathlib import Path

import ahk_workspace_manager.config as config_module
from ahk_workspace_manager.config import AppConfig, ConfigStore, default_config_file


def test_default_config_file_uses_local_app_data(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert default_config_file() == local_app_data / "AHKQuickLaunchManager" / "workspace_manager.json"
    assert ConfigStore().path == local_app_data / "AHKQuickLaunchManager" / "workspace_manager.json"


def test_load_first_run_creates_default_config_and_qdir(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    default_qdir = tmp_path / "Desktop" / "Quick Launch Build Scripts"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(config_module, "DEFAULT_AHK_QDIR", str(default_qdir))
    monkeypatch.chdir(tmp_path)

    store = ConfigStore()
    loaded = store.load()

    assert loaded.ahk_qdir_path == str(default_qdir)
    assert default_qdir.is_dir()
    assert store.path.is_file()


def test_save_creates_config_parent_directory(tmp_path):
    config_path = tmp_path / "missing" / "AHKQuickLaunchManager" / "workspace_manager.json"
    custom_qdir = tmp_path / "custom-qdir"
    config = AppConfig(ahk_qdir_path=str(custom_qdir))

    ConfigStore(config_path).save(config)

    assert config_path.is_file()
    assert json.loads(config_path.read_text(encoding="utf-8"))["ahk_qdir_path"] == str(custom_qdir)


def test_load_migrates_repo_local_config_to_local_app_data(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    old_qdir = tmp_path / "Old QDIR"
    legacy_config = tmp_path / "workspace_manager.json"
    legacy_config.write_text(
        json.dumps(
            {
                "managed_items": [{"name": "Tool", "path": "C:/Tool/tool.ahk", "item_type": "AHK"}],
                "exclusive_groups": {"main": ["tool.ahk"]},
                "show_unmanaged_ahk": False,
                "refresh_interval_ms": 2500,
                "ahk_qdir_path": str(old_qdir),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.chdir(tmp_path)

    store = ConfigStore()
    loaded = store.load()

    assert loaded.ahk_qdir_path == str(old_qdir)
    assert loaded.refresh_interval_ms == 2500
    assert loaded.show_unmanaged_ahk is False
    assert loaded.managed_items[0].name == "Tool"
    assert store.path.is_file()
    assert legacy_config.is_file()


def test_local_app_data_config_wins_over_repo_local_config(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.chdir(tmp_path)
    legacy_config = tmp_path / "workspace_manager.json"
    legacy_config.write_text(json.dumps({"refresh_interval_ms": 1111}), encoding="utf-8")
    local_config = default_config_file()
    local_config.parent.mkdir(parents=True)
    local_config.write_text(json.dumps({"refresh_interval_ms": 2222}), encoding="utf-8")

    loaded = ConfigStore().load()

    assert loaded.refresh_interval_ms == 2222
