from pathlib import Path

from ahk_workspace_manager.qdir_ahk_manager import QdirAhkManager


class FakeProc:
    def __init__(self, pid, cmdline):
        self.info = {"pid": pid, "name": "AutoHotkey.exe", "exe": "AutoHotkey.exe", "cmdline": cmdline}


def test_scan_includes_only_top_level_ahk_files(tmp_path):
    (tmp_path / "FPS.ahk").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "Nested.ahk").write_text("", encoding="utf-8")
    manager = QdirAhkManager()

    scripts = manager.scan(str(tmp_path))

    assert [script.name for script in scripts] == ["FPS.ahk"]


def test_full_path_matching_distinguishes_same_filename(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "Shared.ahk"
    second = second_dir / "Shared.ahk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    manager = QdirAhkManager(process_provider=lambda: [FakeProc(10, ["AutoHotkey.exe", str(second)])])

    running = manager.running_script_pids(manager.scan(str(first_dir)))

    assert manager.normalize_path(str(first)) not in running


def test_start_terminates_other_running_qdir_scripts_before_launch(tmp_path, monkeypatch):
    first = tmp_path / "First.ahk"
    second = tmp_path / "Second.ahk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    launched = []
    stopped = []
    manager = QdirAhkManager(
        process_provider=lambda: [FakeProc(10, ["AutoHotkey.exe", str(first)])],
        launcher=lambda path: launched.append(path),
    )
    monkeypatch.setattr(manager, "stop_pid", lambda pid: stopped.append(pid) or True)
    scripts = manager.scan(str(tmp_path))

    assert manager.start(scripts[1], str(tmp_path)) is True

    assert stopped == [10]
    assert launched == [str(second)]


def test_states_update_when_process_provider_changes(tmp_path):
    script = tmp_path / "FPS.ahk"
    script.write_text("", encoding="utf-8")
    processes = [FakeProc(10, ["AutoHotkey.exe", str(script)])]
    manager = QdirAhkManager(process_provider=lambda: processes)

    assert manager.states(str(tmp_path))[0].status == "RUNNING"

    processes.clear()

    assert manager.states(str(tmp_path))[0].status == "STOPPED"


def test_failed_launch_state_clears_when_script_runs(tmp_path):
    script = tmp_path / "FPS.ahk"
    script.write_text("", encoding="utf-8")
    processes = []

    def fail(_path):
        raise OSError("no association")

    manager = QdirAhkManager(process_provider=lambda: processes, launcher=fail)
    scanned = manager.scan(str(tmp_path))[0]

    assert manager.start(scanned, str(tmp_path)) is False
    assert manager.states(str(tmp_path))[0].status == "FAILED"

    processes.append(FakeProc(10, ["AutoHotkey.exe", str(Path(scanned.path))]))

    assert manager.states(str(tmp_path))[0].status == "RUNNING"


def test_active_script_is_only_visual_running_script(tmp_path):
    first = tmp_path / "First.ahk"
    second = tmp_path / "Second.ahk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    manager = QdirAhkManager(
        process_provider=lambda: [
            FakeProc(10, ["AutoHotkey.exe", str(first)]),
            FakeProc(11, ["AutoHotkey.exe", str(second)]),
        ]
    )
    manager.active_script_path = manager.normalize_path(str(second))

    states = manager.states(str(tmp_path))

    assert [(state.script.name, state.status) for state in states] == [
        ("First.ahk", "STOPPED"),
        ("Second.ahk", "RUNNING"),
    ]


def test_start_sets_new_script_active_and_visually_stops_previous(tmp_path, monkeypatch):
    first = tmp_path / "First.ahk"
    second = tmp_path / "Second.ahk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    launched = []
    manager = QdirAhkManager(
        process_provider=lambda: [
            FakeProc(10, ["AutoHotkey.exe", str(first)]),
            FakeProc(11, ["AutoHotkey.exe", str(second)]),
        ],
        launcher=lambda path: launched.append(path),
    )
    monkeypatch.setattr(manager, "stop_pid", lambda _pid: True)
    second_script = [script for script in manager.scan(str(tmp_path)) if script.name == "Second.ahk"][0]

    assert manager.start(second_script, str(tmp_path)) is True
    states = manager.states(str(tmp_path))

    assert manager.active_script_path == manager.normalize_path(str(second))
    assert [(state.script.name, state.status) for state in states] == [
        ("First.ahk", "STOPPED"),
        ("Second.ahk", "RUNNING"),
    ]


def test_active_script_clears_when_process_disappears(tmp_path):
    script = tmp_path / "FPS.ahk"
    script.write_text("", encoding="utf-8")
    manager = QdirAhkManager(process_provider=lambda: [])
    manager.active_script_path = manager.normalize_path(str(script))

    states = manager.states(str(tmp_path))

    assert manager.active_script_path is None
    assert states[0].status == "STOPPED"


def test_single_external_running_script_is_inferred_active(tmp_path):
    script = tmp_path / "FPS.ahk"
    script.write_text("", encoding="utf-8")
    manager = QdirAhkManager(process_provider=lambda: [FakeProc(10, ["AutoHotkey.exe", str(script)])])

    states = manager.states(str(tmp_path))

    assert manager.active_script_path == manager.normalize_path(str(script))
    assert states[0].status == "RUNNING"
