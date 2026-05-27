# AHK Workspace Manager

Windows PySide6 utility for managed tray/background processes and mutually exclusive AutoHotkey profiles.

## Run

```powershell
python main.py
```

Dependencies are listed in `requirements.txt`.

## MVP Features

- Tray surface accepts `.ahk`, `.exe`, and folders containing both.
- Managed process polling runs every second with visual RUNNING/STOPPED state.
- Current tray/background apps are shown with a live tray monitor and fallback process detection.
- AHK scripts can be assigned to an exclusive group on drop.
- Starting one script in a group terminates the other managed AHK scripts in that group.
- `Kill All` terminates managed processes while skipping essential Windows process names.
- JSON persistence is written per user to `%LOCALAPPDATA%\AHKQuickLaunchManager\workspace_manager.json`.
- First-run AHK launchers use `Desktop\Quick Launch Build Scripts` by default.
- `ADD NEW FILE` creates a `.ahk` launcher for a selected Python project folder containing `main.py`.
