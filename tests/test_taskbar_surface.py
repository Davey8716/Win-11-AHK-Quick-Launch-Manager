import pytest
from PySide6.QtWidgets import QApplication

from ahk_workspace_manager.config import AppConfig, TaskbarItem
from ahk_workspace_manager.ui import TaskbarSurface


@pytest.fixture
def app():
    existing = QApplication.instance()
    return existing or QApplication([])


class FakeStore:
    def __init__(self):
        self.saved = []

    def save(self, config):
        self.saved.append(config)


class FakeTaskbarManager:
    def __init__(self, config):
        self.config = config
        self.pinned = []

    def add_path(self, path):
        return []

    def pin(self, path):
        self.pinned.append(path)
        return True

    def pin_all(self):
        for item in self.config.taskbar_items:
            item.pinned = True

    def unpin_all(self):
        for item in self.config.taskbar_items:
            item.pinned = False

    def remove(self, item):
        self.config.taskbar_items = [existing for existing in self.config.taskbar_items if existing.path != item.path]

    def remove_all(self):
        self.config.taskbar_items.clear()


def test_pin_selected_only_pins_highlighted_item(app, tmp_path):
    first = tmp_path / "first.exe"
    second = tmp_path / "second.exe"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    config = AppConfig(
        taskbar_items=[
            TaskbarItem(name="First", path=str(first)),
            TaskbarItem(name="Second", path=str(second)),
        ]
    )
    manager = FakeTaskbarManager(config)
    surface = TaskbarSurface(config, FakeStore(), manager)

    assert surface.pin_button.isEnabled() is False

    surface.select_item(config.taskbar_items[1])
    surface.pin_selected()

    assert manager.pinned == [str(second)]
    assert config.taskbar_items[1].pinned is True


def test_remove_all_clears_surface_items(app, tmp_path):
    target = tmp_path / "tool.exe"
    target.write_text("", encoding="utf-8")
    config = AppConfig(taskbar_items=[TaskbarItem(name="Tool", path=str(target))])
    surface = TaskbarSurface(config, FakeStore(), FakeTaskbarManager(config))

    surface.select_item(config.taskbar_items[0])
    surface.remove_all()

    assert config.taskbar_items == []
    assert surface.selected_path is None
    assert surface.pin_button.isEnabled() is False
