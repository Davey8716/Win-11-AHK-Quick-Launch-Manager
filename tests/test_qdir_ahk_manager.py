import ahk_workspace_manager.qdir_ahk_manager as qdir_module
from ahk_workspace_manager.qdir_ahk_manager import QdirAhkManager, QdirAhkScript


def test_create_project_launcher_writes_default_template(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "Energy_Saver_App"
    qdir = tmp_path / "Quick Launch Build Scripts"
    project.mkdir(parents=True)
    qdir.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    script = QdirAhkManager().create_project_launcher(str(project), str(qdir))

    assert script.name == "Energy_Saver_App.ahk"
    assert (qdir / script.name).read_text(encoding="utf-8") == (
        "#Requires AutoHotkey v1.1\n\n"
        f'project := "{project / "main.py"}"\n\n'
        "^XButton1::\n"
        'Run, wt.exe python "%project%"\n'
        "return\n\n"
        "XButton2::\n"
        'Run, pythonw.exe "%project%"\n'
        "return\n\n"
        "XButton1::\n"
        "Run, taskkill /IM pythonw.exe /F\n"
        "return\n"
    )


def test_stop_pid_kills_without_waiting(monkeypatch):
    events = []

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def kill(self):
            events.append(("kill", self.pid))

        def wait(self, timeout=None):
            raise AssertionError("stop_pid should not wait")

    monkeypatch.setattr(qdir_module.psutil, "Process", FakeProcess)

    assert QdirAhkManager().stop_pid(123) is True
    assert events == [("kill", 123)]


def test_start_kills_running_script_before_launch_without_waiting(tmp_path, monkeypatch):
    events = []
    first = tmp_path / "first.ahk"
    second = tmp_path / "second.ahk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    class FakeProcInfo:
        info = {"pid": 456, "cmdline": [str(first)]}

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def kill(self):
            events.append(("kill", self.pid))

        def wait(self, timeout=None):
            raise AssertionError("start switching should not wait")

    monkeypatch.setattr(qdir_module.psutil, "Process", FakeProcess)
    manager = QdirAhkManager(
        process_provider=lambda: [FakeProcInfo()],
        launcher=lambda path: events.append(("launch", path)),
    )

    assert manager.start(QdirAhkScript(name=second.name, path=str(second)), str(tmp_path)) is True
    assert events == [("kill", 456), ("launch", str(second))]
