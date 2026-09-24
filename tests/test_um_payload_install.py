"""UM zip payload: find UpdateManager/ and install into manager dir."""

from __future__ import annotations

from pathlib import Path

from update_manager.apply import find_um_payload, install_manager_payload
from update_manager.paths import UM_BAT_NAME, UM_EXE_NAME, UM_VBS_NAME


def _make_payload(root: Path) -> Path:
    um = root / "UpdateManager"
    um.mkdir(parents=True)
    (um / UM_EXE_NAME).write_bytes(b"MZ-new")
    (um / UM_BAT_NAME).write_text("@echo off\n", encoding="utf-8")
    (um / UM_VBS_NAME).write_text("' hidden\n", encoding="utf-8")
    return um


def test_find_um_payload_sibling_of_onedir(tmp_path: Path) -> None:
    stage = tmp_path / "extract"
    app = stage / "CloneUp"
    app.mkdir(parents=True)
    (app / "CloneUp.exe").write_bytes(b"MZ")
    _make_payload(stage)
    found = find_um_payload(app)
    assert found is not None
    assert (found / UM_EXE_NAME).is_file()


def test_find_um_payload_missing(tmp_path: Path) -> None:
    app = tmp_path / "CloneUp"
    app.mkdir()
    (app / "CloneUp.exe").write_bytes(b"MZ")
    assert find_um_payload(app) is None


def test_install_manager_payload_copies_launchers(
    monkeypatch, tmp_path: Path
) -> None:
    src = _make_payload(tmp_path / "src")
    dest = tmp_path / "ProgramData" / "CloneUp" / "UpdateManager"
    dest.mkdir(parents=True)
    (dest / UM_EXE_NAME).write_bytes(b"MZ-old")

    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    # No running lock — rename of dest exe should succeed
    exit_req = install_manager_payload(src)
    assert (dest / UM_BAT_NAME).is_file()
    assert (dest / UM_VBS_NAME).is_file()
    assert (dest / UM_EXE_NAME).read_bytes() == b"MZ-new"
    # Renamed old → request_exit True when old existed
    assert exit_req is True
