import ahk_workspace_manager.qdir_ahk_manager as qdir_module
from ahk_workspace_manager.qdir_ahk_manager import QdirAhkManager


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
