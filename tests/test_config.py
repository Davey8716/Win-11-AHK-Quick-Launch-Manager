from ahk_workspace_manager.config import AppConfig, ConfigStore, ManagedItem, TaskbarItem


def test_config_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(
        taskbar_items=[TaskbarItem(name="Blender", path="C:/Tools/blender.exe", pinned=True)],
        managed_items=[ManagedItem(name="FPS.ahk", path="C:/Scripts/FPS.ahk", item_type="AHK", group="thumb_buttons")],
        exclusive_groups={"thumb_buttons": ["FPS.ahk"]},
    )

    store = ConfigStore(path)
    store.save(config)

    loaded = store.load()

    assert loaded.taskbar_items[0].name == "Blender"
    assert loaded.taskbar_items[0].pinned is True
    assert loaded.managed_items[0].group == "thumb_buttons"
    assert loaded.exclusive_groups == {"thumb_buttons": ["FPS.ahk"]}

