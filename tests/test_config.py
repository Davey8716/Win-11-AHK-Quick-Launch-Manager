from ahk_workspace_manager.config import AppConfig, ConfigStore, ManagedItem


def test_config_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(
        managed_items=[ManagedItem(name="FPS.ahk", path="C:/Scripts/FPS.ahk", item_type="AHK", group="thumb_buttons")],
        exclusive_groups={"thumb_buttons": ["FPS.ahk"]},
        refresh_interval_ms=1500,
    )

    store = ConfigStore(path)
    store.save(config)

    loaded = store.load()

    assert loaded.managed_items[0].group == "thumb_buttons"
    assert loaded.exclusive_groups == {"thumb_buttons": ["FPS.ahk"]}
    assert loaded.refresh_interval_ms == 1500


def test_config_ignores_stale_taskbar_items(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        """
        {
          "taskbar_items": [{"name": "Old", "path": "C:/Old.exe"}],
          "managed_items": [],
          "exclusive_groups": {},
          "show_unmanaged_ahk": true,
          "refresh_interval_ms": 1000
        }
        """,
        encoding="utf-8",
    )

    loaded = ConfigStore(path).load()

    assert loaded.managed_items == []
