# AHK Quick Launch Manager

A tiny Windows tray app for AutoHotkey users who jump between Python main.py projects and want one active quick-launch profile at a time.

Windows-only PySide6 utility for a very specific workflow: managing a folder of AutoHotkey launchers that start Python `main.py` projects.

This is not a general launcher. It is for users who keep many small Python desktop tools or automation projects and want a quick, mouse-button-driven way to switch which AutoHotkey launcher is active. The app is intentionally centered on one active `.ahk` launcher at a time.

## What It Does

- Watches a chosen QDIR folder for `.ahk` files.
- Shows each launcher as `RUNNING`, `STOPPED`, or `FAILED`.
- Starts one launcher while stopping other running launchers from the same folder.
- Generates new `.ahk` launcher files for Python project folders that contain `main.py`.
- Runs from the Windows tray and restores the existing window when a second instance is launched.
- Stores settings per Windows user.

## First Run

On first run, the app creates and uses this default launcher folder:

```text
%USERPROFILE%\Desktop\Quick Launch Build Scripts
```

The app config is stored here:

```text
%LOCALAPPDATA%\AHKQuickLaunchManager\workspace_manager.json
```

An old repo-local `workspace_manager.json` is migrated into the per-user config location if the new config file does not exist yet. The old file is not deleted.

## Main Workflow

1. Run the app.
2. Click `ADD NEW FILE`.
3. Select a Python project folder that contains `main.py`.
4. The app writes a generated `.ahk` launcher into the QDIR folder.
5. Use `START` and `STOP` in the app to control which launcher is active.

Starting one launcher stops the other running QDIR launchers first. The stop path is intentionally forceful and fast for AutoHotkey script processes.

## Generated Launcher Hotkeys

Each generated `.ahk` file uses AutoHotkey v1.1 syntax and this behavior:

```text
Ctrl+XButton1 -> wt.exe python "%project%"
XButton2      -> pythonw.exe "%project%"
XButton1      -> taskkill /IM pythonw.exe /F
```

The generated script points `project` at the selected project folder's `main.py`.

Important: the `XButton1` kill hotkey runs `taskkill /IM pythonw.exe /F`, which can terminate unrelated `pythonw.exe` processes. This app is not appropriate if that global kill behavior is unacceptable.

## Controls

- `OPEN CONFIG LOCATION`: opens `%LOCALAPPDATA%\AHKQuickLaunchManager`.
- `PICK DIRECTORY`: changes the QDIR folder that contains `.ahk` launchers.
- `ADD NEW FILE`: creates a generated launcher for a selected Python project containing `main.py`.
- `START`: starts that launcher and stops other running QDIR launchers.
- `STOP`: stops that launcher's AutoHotkey process.

Closing the window hides it to the tray when the system tray is available. Use the tray menu to reopen or exit. Launching the app again restores the existing instance instead of opening a second copy.

## Requirements

- Windows
- Python
- AutoHotkey v1.1 for generated scripts
- Windows Terminal if you use the `Ctrl+XButton1` terminal hotkey

Python dependencies are listed in `requirements.txt`:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## What This Is Not

- Not a general process manager.
- Not a cross-platform launcher.
- Not a general AutoHotkey editor.
- Not a safe choice for users who do not want the generated `pythonw.exe` kill hotkey.

## Developer Notes

The active UI is the QDIR AutoHotkey launcher surface in `ahk_workspace_manager/ui.py` backed by `QdirAhkManager`.

`process_manager.py` and `tray_monitor.py` still exist in the repo, but they are not the primary visible workflow in the current window. Treat them as supporting or legacy/internal code unless they are deliberately reconnected to the UI.
