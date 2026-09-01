"""Unit tests for independent update_manager (no live GitHub / no kill)."""

from __future__ import annotations

from pathlib import Path

import pytest

from update_manager.apply import _find_onedir_root, copy_onedir_into
from update_manager.github_release import host_allowed
from update_manager.paths import find_cloneup_install_dir
from update_manager.versioning import is_newer, normalize_version


def test_normalize_version_tags() -> None:
    assert normalize_version("v0.1.8") == (0, 1, 8)
    assert normalize_version("0.1.9") == (0, 1, 9)
    assert normalize_version("CloneUp 0.1.8") == (0, 1, 8)
    assert normalize_version("nope") is None


def test_is_newer() -> None:
    assert is_newer((0, 1, 9), (0, 1, 8)) is True
    assert is_newer((0, 1, 8), (0, 1, 8)) is False
    assert is_newer((0, 1, 7), (0, 1, 8)) is False


def test_host_allowed() -> None:
    assert host_allowed("https://github.com/seongbin45/CloneUp/releases/download/x/y.zip")
    assert host_allowed(
        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/x"
    )
    assert not host_allowed("https://evil.example/x.zip")


def test_find_install_dir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "CloneUp"
    app.mkdir()
    (app / "CloneUp.exe").write_bytes(b"MZ")
    monkeypatch.setenv("CLONEUP_INSTALL_DIR", str(app))
    got = find_cloneup_install_dir()
    assert got is not None
    assert got == app.resolve()


def test_find_install_dir_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CLONEUP_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    # Empty registry scan may still find a real install on this machine —
    # only assert env override path works when set; for missing, call is allowed.
    # Force env empty dir that does not look like install:
    bad = tmp_path / "empty"
    bad.mkdir()
    monkeypatch.setenv("CLONEUP_INSTALL_DIR", str(bad))
    assert find_cloneup_install_dir() is None


def test_copy_onedir_flat(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "CloneUp.exe").write_text("exe", encoding="utf-8")
    (src / "VERSION").write_text("0.1.9\n", encoding="utf-8")
    sub = src / "_internal"
    sub.mkdir()
    (sub / "x.txt").write_text("1", encoding="utf-8")

    dest = tmp_path / "install"
    dest.mkdir()
    (dest / "old.txt").write_text("old", encoding="utf-8")

    copy_onedir_into(src, dest)
    assert (dest / "CloneUp.exe").read_text(encoding="utf-8") == "exe"
    assert (dest / "VERSION").read_text(encoding="utf-8").startswith("0.1.9")
    assert (dest / "_internal" / "x.txt").is_file()
    assert not (dest / "old.txt").exists()


def test_find_onedir_root_nested(tmp_path: Path) -> None:
    root = tmp_path / "extract"
    nested = root / "CloneUp"
    nested.mkdir(parents=True)
    (nested / "CloneUp.exe").write_bytes(b"MZ")
    assert _find_onedir_root(root) == nested
