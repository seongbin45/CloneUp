"""받기 탭 커밋 내역: detect an already-cloned local folder for a GitHub URL."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.runner import run_git
from app.ui.main_window import MainController


def _git_ok() -> bool:
    try:
        run_git(["--version"], cwd=None, check=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git required")


def _init_repo_with_origin(folder: Path, origin: str) -> None:
    run_git(["init", "-b", "main"], cwd=str(folder), check=True)
    run_git(["config", "user.name", "T"], cwd=str(folder), check=True)
    run_git(["config", "user.email", "t@example.com"], cwd=str(folder), check=True)
    (folder / "a.txt").write_text("x\n", encoding="utf-8")
    run_git(["add", "-A"], cwd=str(folder), check=True)
    run_git(["commit", "-m", "c1"], cwd=str(folder), check=True)
    run_git(["remote", "add", "origin", origin], cwd=str(folder), check=True)


@requires_git
def test_matching_local_clone_is_detected(tmp_path: Path) -> None:
    _init_repo_with_origin(
        tmp_path, "https://github.com/seongbin45/cloneup-fake-repo.git"
    )
    found = MainController._local_clone_for_url(
        tmp_path, "seongbin45", "cloneup-fake-repo"
    )
    assert found == str(tmp_path)


@requires_git
def test_case_insensitive_match(tmp_path: Path) -> None:
    _init_repo_with_origin(
        tmp_path, "https://github.com/SeongBin45/CloneUp-Fake-Repo.git"
    )
    found = MainController._local_clone_for_url(
        tmp_path, "seongbin45", "cloneup-fake-repo"
    )
    assert found == str(tmp_path)


@requires_git
def test_different_repo_is_rejected(tmp_path: Path) -> None:
    _init_repo_with_origin(
        tmp_path, "https://github.com/someone-else/other-repo.git"
    )
    found = MainController._local_clone_for_url(
        tmp_path, "seongbin45", "cloneup-fake-repo"
    )
    assert found is None


def test_missing_folder_is_none(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    found = MainController._local_clone_for_url(
        missing, "seongbin45", "cloneup-fake-repo"
    )
    assert found is None


def test_folder_without_git_is_none(tmp_path: Path) -> None:
    (tmp_path / "not-a-repo.txt").write_text("x\n", encoding="utf-8")
    found = MainController._local_clone_for_url(
        tmp_path, "seongbin45", "cloneup-fake-repo"
    )
    assert found is None


@requires_git
def test_find_local_clone_falls_back_to_recent_folders(tmp_path: Path) -> None:
    """
    Regression: editCloneParent/editCloneDirName reset every app restart (not
    settings-backed), so a clone from a *previous* session must still be
    found via 최근 폴더 — not just whatever the 받기 탭 fields show right now.
    """
    import os

    import pytest

    # Full QUiLoader + MainController has hung GHA windows jobs; unit-test the
    # path finder instead of loading the whole shell on CI.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.skip("load_main_window is too heavy / flaky on GHA windows-latest")

    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import load_main_window
    from app.ui.settings_store import _settings, remember_folder

    QApplication.instance() or QApplication([])

    clone_dir = tmp_path / "old-session-clone"
    clone_dir.mkdir()
    _init_repo_with_origin(
        clone_dir, "https://github.com/seongbin45/cloneup-fake-repo.git"
    )

    s = _settings()
    prev = s.value("recent_folders")
    try:
        s.setValue("recent_folders", [])
        remember_folder(str(clone_dir))

        window = load_main_window()
        ctrl = window._cloneup_controller
        # 받기 탭 fields point somewhere unrelated — simulates a fresh session
        ctrl.editCloneParent.setText(str(tmp_path / "somewhere-else"))
        ctrl.editCloneDirName.setText("")

        found = ctrl._find_local_clone_for_url("seongbin45", "cloneup-fake-repo")
        assert found == str(clone_dir)
        window.close()
    finally:
        if prev is None:
            s.remove("recent_folders")
        else:
            s.setValue("recent_folders", prev)
