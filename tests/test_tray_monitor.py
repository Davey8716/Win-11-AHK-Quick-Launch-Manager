from ahk_workspace_manager.tray_monitor import TrayIconMonitor


def test_fallback_filter_excludes_core_windows_process():
    monitor = TrayIconMonitor()

    assert (
        monitor._is_fallback_candidate(
            {
                "pid": 10,
                "name": "svchost.exe",
                "exe": "C:\\Windows\\System32\\svchost.exe",
                "cmdline": [],
            },
            {10},
        )
        is False
    )


def test_fallback_filter_includes_user_gui_process():
    monitor = TrayIconMonitor()

    assert (
        monitor._is_fallback_candidate(
            {
                "pid": 25,
                "name": "Example.exe",
                "exe": "C:\\Users\\davey\\AppData\\Local\\Example\\Example.exe",
                "cmdline": [],
            },
            {25},
        )
        is True
    )


def test_fallback_filter_includes_ahk_script_process():
    monitor = TrayIconMonitor()

    assert (
        monitor._is_fallback_candidate(
            {
                "pid": 30,
                "name": "AutoHotkey64.exe",
                "exe": "C:\\Tools\\AutoHotkey\\AutoHotkey64.exe",
                "cmdline": ["AutoHotkey64.exe", "C:\\Scripts\\FPS.ahk"],
            },
            set(),
        )
        is True
    )


def test_fallback_filter_excludes_service_like_user_process():
    monitor = TrayIconMonitor()

    assert (
        monitor._is_fallback_candidate(
            {
                "pid": 45,
                "name": "ExampleService.exe",
                "exe": "C:\\Program Files\\Example\\ExampleService.exe",
                "cmdline": [],
            },
            set(),
        )
        is False
    )


def test_fallback_filter_excludes_helper_path_without_window():
    monitor = TrayIconMonitor()

    assert (
        monitor._is_fallback_candidate(
            {
                "pid": 50,
                "name": "OpenConsole.exe",
                "exe": "C:\\Users\\davey\\AppData\\Local\\Programs\\App\\node_modules\\OpenConsole.exe",
                "cmdline": [],
            },
            set(),
        )
        is False
    )


def test_fallback_dedupes_by_executable_path(monkeypatch):
    monitor = TrayIconMonitor()

    class FakeProc:
        def __init__(self, pid):
            self.info = {
                "pid": pid,
                "name": "Example.exe",
                "exe": "C:\\Users\\davey\\AppData\\Local\\Example\\Example.exe",
                "cmdline": [],
            }

    monkeypatch.setattr("psutil.process_iter", lambda _attrs: [FakeProc(1), FakeProc(2)])
    monkeypatch.setattr(monitor, "_window_process_ids", lambda: {1, 2})

    icons = monitor.fallback_icons()

    assert len(icons) == 1
    assert icons[0].pid == 1
