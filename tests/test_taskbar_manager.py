from pathlib import Path

import pytest

from ahk_workspace_manager.config import AppConfig, TaskbarItem
from ahk_workspace_manager.taskbar_manager import TaskbarManager


def test_remove_all_clears_taskbar_items():
    config = AppConfig(
        taskbar_items=[
            TaskbarItem(name="One", path="C:/Tools/one.exe"),
            TaskbarItem(name="Two", path="C:/Tools/two.exe"),
        ]
    )
    manager = TaskbarManager(config)

    manager.remove_all()

    assert config.taskbar_items == []


def test_pinned_shortcut_path_uses_target_stem(tmp_path):
    manager = TaskbarManager(AppConfig(), pinned_dir=tmp_path)

    shortcut_path = manager.pinned_shortcut_path("C:/Program Files/App/app.exe")

    assert shortcut_path == tmp_path / "app.lnk"


def test_shortcut_fallback_creates_lnk_for_exe(tmp_path):
    pytest.importorskip("win32com.client")
    exe = tmp_path / "tool.exe"
    exe.write_text("", encoding="utf-8")
    manager = TaskbarManager(AppConfig(), pinned_dir=tmp_path / "pinned")

    assert manager._create_pinned_shortcut(str(exe)) is True

    assert (tmp_path / "pinned" / "tool.lnk").exists()


def test_shortcut_fallback_copies_lnk(tmp_path):
    source = tmp_path / "source.lnk"
    source.write_text("shortcut", encoding="utf-8")
    manager = TaskbarManager(AppConfig(), pinned_dir=tmp_path / "pinned")

    assert manager._create_pinned_shortcut(str(source)) is True

    assert Path(tmp_path / "pinned" / "source.lnk").read_text(encoding="utf-8") == "shortcut"

