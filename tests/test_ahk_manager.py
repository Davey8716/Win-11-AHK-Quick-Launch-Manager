from ahk_workspace_manager.ahk_manager import AHKManager
from ahk_workspace_manager.config import AppConfig, ManagedItem


class FakeProcessManager:
    def __init__(self):
        self.terminated = []
        self.launched = []

    def terminate(self, item):
        self.terminated.append(item.name)
        return True

    def launch(self, item):
        self.launched.append(item.name)
        return 100


def test_start_terminates_other_scripts_in_exclusive_group():
    fps = ManagedItem(name="FPS.ahk", path="C:/Scripts/FPS.ahk", item_type="AHK", group="thumb_buttons")
    mmo = ManagedItem(name="MMO.ahk", path="C:/Scripts/MMO.ahk", item_type="AHK", group="thumb_buttons")
    editing = ManagedItem(name="Editing.ahk", path="C:/Scripts/Editing.ahk", item_type="AHK", group="thumb_buttons")
    config = AppConfig(
        managed_items=[fps, mmo, editing],
        exclusive_groups={"thumb_buttons": ["FPS.ahk", "MMO.ahk", "Editing.ahk"]},
    )
    process_manager = FakeProcessManager()
    manager = AHKManager(config, process_manager)

    manager.start(mmo)

    assert process_manager.terminated == ["FPS.ahk", "Editing.ahk"]
    assert process_manager.launched == ["MMO.ahk"]

