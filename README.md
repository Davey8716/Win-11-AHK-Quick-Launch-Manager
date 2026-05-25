# AHK Workspace Manager

Windows PySide6 utility for fast taskbar pin registration, managed tray/background processes, and mutually exclusive AutoHotkey profiles.

## Run

```powershell
python main.py
```

Dependencies are listed in `requirements.txt`.

## MVP Features

- Two stacked surfaces with a resizable vertical splitter.
- Taskbar surface accepts `.exe`, `.lnk`, and folders containing executables.
- Tray surface accepts `.ahk`, `.exe`, and folders containing both.
- Managed process polling runs every second with visual RUNNING/STOPPED state.
- AHK scripts can be assigned to an exclusive group on drop.
- Starting one script in a group terminates the other managed AHK scripts in that group.
- `Kill All` terminates managed processes while skipping essential Windows process names.
- JSON persistence is written to `workspace_manager.json`.

## Notes

Taskbar pin and unpin actions use Windows shell verbs on a best-effort basis. Microsoft does not provide a stable public API for arbitrary taskbar pinning, and shell verb behavior can vary by Windows build and policy.

