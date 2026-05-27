from pathlib import Path

import pytest

import ahk_workspace_manager.qdir_ahk_manager as qdir_module
from ahk_workspace_manager.qdir_ahk_manager import QdirAhkCreateError, QdirAhkManager


def test_create_project_launcher_writes_expected_script(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "Win-11-Python-EXE-Builder"
    qdir = tmp_path / "Quick Launch Build Scripts"
    project.mkdir(parents=True)
    qdir.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    script = QdirAhkManager().create_project_launcher(str(project), str(qdir))

    assert script.name == "Win-11-Python-EXE-Builder.ahk"
    script_path = qdir / script.name
    assert script.path == str(script_path)
    assert script_path.read_text(encoding="utf-8") == (
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


def test_create_project_launcher_names_nested_project_from_relative_path(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "Tools" / "Builder"
    qdir = tmp_path / "qdir"
    project.mkdir(parents=True)
    qdir.mkdir()
    (project / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    script = QdirAhkManager().create_project_launcher(str(project), str(qdir))

    assert script.name == "Tools - Builder.ahk"


def test_create_project_launcher_uses_folder_name_outside_projects_root(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = tmp_path / "Elsewhere" / "Standalone"
    qdir = tmp_path / "qdir"
    project.mkdir(parents=True)
    qdir.mkdir()
    (project / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    script = QdirAhkManager().create_project_launcher(str(project), str(qdir))

    assert script.name == "Standalone.ahk"


def test_create_project_launcher_refuses_to_overwrite_existing_script(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "Existing"
    qdir = tmp_path / "qdir"
    project.mkdir(parents=True)
    qdir.mkdir()
    (project / "main.py").write_text("", encoding="utf-8")
    existing = qdir / "Existing.ahk"
    existing.write_text("keep me", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    with pytest.raises(QdirAhkCreateError, match="already exists"):
        QdirAhkManager().create_project_launcher(str(project), str(qdir))

    assert existing.read_text(encoding="utf-8") == "keep me"


def test_create_project_launcher_refuses_project_without_main_py(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "MissingMain"
    qdir = tmp_path / "qdir"
    project.mkdir(parents=True)
    qdir.mkdir()
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    with pytest.raises(QdirAhkCreateError, match="main.py"):
        QdirAhkManager().create_project_launcher(str(project), str(qdir))


def test_create_project_launcher_refuses_missing_qdir(tmp_path, monkeypatch):
    projects_root = tmp_path / "Desktop" / "Projects"
    project = projects_root / "Project"
    qdir = tmp_path / "missing-qdir"
    project.mkdir(parents=True)
    (project / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(qdir_module, "PROJECTS_ROOT", projects_root)

    with pytest.raises(QdirAhkCreateError, match="AHK directory"):
        QdirAhkManager().create_project_launcher(str(project), str(qdir))


def test_create_project_launcher_refuses_empty_generated_filename(tmp_path, monkeypatch):
    project = tmp_path / "Project"
    qdir = tmp_path / "qdir"
    project.mkdir()
    qdir.mkdir()
    (project / "main.py").write_text("", encoding="utf-8")
    manager = QdirAhkManager()
    monkeypatch.setattr(manager, "_project_launcher_filename_stem", lambda project_root: "")

    with pytest.raises(QdirAhkCreateError, match="valid AHK filename"):
        manager.create_project_launcher(str(project), str(qdir))
