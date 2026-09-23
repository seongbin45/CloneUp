"""Large-file classifier + untrack helpers (plan rev.3 S0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.large_files import (
    BLOCK_BYTES,
    WARN_BYTES,
    LargeKind,
    classify_size,
    find_working_tree_large_files,
    format_warn_log_line,
    gitignore_exact_line,
    is_github_size_limit_error,
    is_lfs_pointer_file,
)
from app.git.runner import run_git
from app.git.untrack import append_exact_gitignore, untrack_worktree


def test_classify_size_strict_gt() -> None:
    assert classify_size(WARN_BYTES) is LargeKind.OK
    assert classify_size(WARN_BYTES + 1) is LargeKind.WARN
    assert classify_size(BLOCK_BYTES) is LargeKind.WARN
    assert classify_size(BLOCK_BYTES + 1) is LargeKind.BLOCK


def test_gitignore_exact_line() -> None:
    assert gitignore_exact_line("assets/video.mp4") == "/assets/video.mp4"
    assert gitignore_exact_line("/assets/video.mp4") == "/assets/video.mp4"


def test_lfs_pointer_skip(tmp_path: Path) -> None:
    p = tmp_path / "big.bin"
    p.write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:" + ("a" * 64) + "\n"
        "size 999999999\n",
        encoding="utf-8",
    )
    assert is_lfs_pointer_file(p) is True
    (tmp_path / "real.bin").write_bytes(b"x" * 100)
    assert is_lfs_pointer_file(tmp_path / "real.bin") is False


def test_find_working_tree_block_and_warn(tmp_path: Path) -> None:
    # Use explicit paths + truncate to avoid writing huge files.
    warn_f = tmp_path / "warn.bin"
    block_f = tmp_path / "block.bin"
    ok_f = tmp_path / "ok.bin"
    warn_f.write_bytes(b"\0")
    block_f.write_bytes(b"\0")
    ok_f.write_bytes(b"\0")
    # Sparse-ish: set size via truncate
    with warn_f.open("r+b") as f:
        f.truncate(WARN_BYTES + 1)
    with block_f.open("r+b") as f:
        f.truncate(BLOCK_BYTES + 1)
    with ok_f.open("r+b") as f:
        f.truncate(WARN_BYTES)

    warns, blocks = find_working_tree_large_files(
        tmp_path,
        paths=["warn.bin", "block.bin", "ok.bin"],
    )
    assert [h.rel for h in warns] == ["warn.bin"]
    assert [h.rel for h in blocks] == ["block.bin"]
    assert "권장 크기" in format_warn_log_line(warns[0])


def test_is_github_size_limit_error() -> None:
    assert is_github_size_limit_error(
        "remote: error: File x is 123.00 MB; this exceeds GitHub's file size limit of 100.00 MB"
    )
    assert is_github_size_limit_error("GH001: Large files detected")
    assert not is_github_size_limit_error("Authentication failed")


def test_untrack_worktree_keeps_disk_file(tmp_path: Path) -> None:
    run_git(["init"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.email", "t@t.com"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.name", "t"], cwd=str(tmp_path), check=True)
    big = tmp_path / "clip.mp4"
    big.write_bytes(b"video")
    run_git(["add", "clip.mp4"], cwd=str(tmp_path), check=True)
    run_git(["commit", "-m", "add"], cwd=str(tmp_path), check=True)

    untrack_worktree(tmp_path, ["clip.mp4"], commit=True)
    assert big.is_file()  # --cached must keep disk bytes
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "/clip.mp4" in gi
    # no longer staged/tracked as content
    r = run_git(["ls-files", "--", "clip.mp4"], cwd=str(tmp_path), check=False)
    assert (r.stdout or "").strip() == ""


def test_append_exact_gitignore_idempotent(tmp_path: Path) -> None:
    a1 = append_exact_gitignore(tmp_path, ["a/b.bin"])
    a2 = append_exact_gitignore(tmp_path, ["a/b.bin"])
    assert a1 == ["/a/b.bin"]
    assert a2 == []
