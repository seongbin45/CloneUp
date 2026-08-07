"""Read-only commit history helpers (list / changed files / export tree).

Used by the 커밋 내역 dialog. Never mutates the working tree of *folder*.
"""

from __future__ import annotations

import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.git.runner import GitError, run_git

# Field separator unlikely in author/subject (ASCII unit separator)
_FS = "\x1f"


@dataclass(frozen=True)
class ChangedFile:
    kind: str  # A | M | D | R | C | T | U | ?
    path: str


@dataclass
class CommitInfo:
    full_hash: str
    short_hash: str
    author: str
    unix_time: int
    abs_time: str
    message: str
    file_count: int = 0
    changed: list[ChangedFile] = field(default_factory=list)


def relative_time_ko(unix_time: int, *, now: float | None = None) -> str:
    """Beginner-friendly relative Korean labels."""
    t0 = time.time() if now is None else now
    delta = max(0, int(t0 - unix_time))
    if delta < 60:
        return "방금"
    if delta < 3600:
        return f"{delta // 60}분 전"
    if delta < 86400:
        return f"{delta // 3600}시간 전"
    days = delta // 86400
    if days < 14:
        return f"{days}일 전"
    if days < 60:
        return f"{days // 7}주 전"
    months = days // 30
    if months < 18:
        return f"{months}개월 전"
    return f"{days // 365}년 전"


def format_abs_time(unix_time: int) -> str:
    """Compact local time like design mock: 8/7 14:02"""
    dt = datetime.fromtimestamp(unix_time)
    return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"


def parse_log_line(line: str) -> CommitInfo | None:
    """Parse one line from our custom git log format."""
    parts = line.split(_FS)
    if len(parts) < 6:
        return None
    full, short, author, at_s, _ad, subject = (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
    try:
        unix = int(at_s)
    except ValueError:
        return None
    full = full.strip()
    if not full:
        return None
    return CommitInfo(
        full_hash=full,
        short_hash=(short or full[:7]).strip(),
        author=(author or "").strip() or "(작성자 없음)",
        unix_time=unix,
        abs_time=format_abs_time(unix),
        message=(subject or "").strip() or "(메시지 없음)",
    )


def list_commits(
    folder: str | Path,
    *,
    limit: int = 20,
    skip: int = 0,
) -> list[CommitInfo]:
    """
    Newest-first commit list for a local git repo.

    ``limit`` / ``skip`` support paged “더 보기”.
    """
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise GitError("폴더가 없습니다.")
    if not (root / ".git").exists():
        raise GitError("이 폴더는 Git 저장소가 아닙니다. (.git 없음)")

    # %H full, %h short, %an author, %at unix, %ad date string, %s subject
    fmt = f"%H{_FS}%h{_FS}%an{_FS}%at{_FS}%ad{_FS}%s"
    r = run_git(
        [
            "log",
            f"--skip={max(0, skip)}",
            f"-n{max(1, limit)}",
            f"--pretty=format:{fmt}",
            "--date=format:%m/%d %H:%M",
        ],
        cwd=str(root),
        check=True,
        config=[("log.showSignature", "false")],
    )
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    out: list[CommitInfo] = []
    for ln in lines:
        info = parse_log_line(ln)
        if info is None:
            continue
        # File count for list row (cheap name-only)
        try:
            info.file_count = count_changed_files(root, info.full_hash)
        except GitError:
            info.file_count = 0
        out.append(info)
    return out


def count_changed_files(folder: str | Path, rev: str) -> int:
    # --root: first commit has no parent; without it, name-only is empty
    r = run_git(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", rev],
        cwd=str(folder),
        check=True,
    )
    return sum(1 for ln in (r.stdout or "").splitlines() if ln.strip())


def list_changed_files(folder: str | Path, rev: str) -> list[ChangedFile]:
    """Name-status for one commit (A/M/D/…)."""
    # --root required so the initial commit lists added files
    r = run_git(
        ["diff-tree", "--no-commit-id", "--name-status", "-r", "-z", "--root", rev],
        cwd=str(folder),
        check=True,
    )
    raw = r.stdout or ""
    # -z: status\0path\0  or R100\0old\0new\0
    parts = [p for p in raw.split("\0") if p != ""]
    out: list[ChangedFile] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        i += 1
        if not status:
            continue
        kind = status[0].upper() if status else "?"
        if kind in ("R", "C") and i + 1 < len(parts):
            # rename/copy: old new — show new path with R/C
            _old = parts[i]
            new = parts[i + 1]
            i += 2
            out.append(ChangedFile(kind=kind, path=new))
        elif i < len(parts):
            path = parts[i]
            i += 1
            out.append(ChangedFile(kind=kind if kind.isalpha() else "?", path=path))
        else:
            break
    return out


def export_commit_snapshot(folder: str | Path, rev: str) -> Path:
    """
    Export tree at *rev* into a new temp folder (read-only view).

    Working tree of *folder* is never modified. Returns extract directory.
    """
    root = Path(folder).expanduser().resolve()
    dest = Path(tempfile.mkdtemp(prefix="CloneUp-view-"))
    zip_path = dest / "_tree.zip"
    try:
        run_git(
            ["archive", "--format=zip", f"--output={zip_path}", rev],
            cwd=str(root),
            check=True,
            timeout=180,
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest)
    except Exception:
        # Best-effort cleanup of incomplete extract
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
    return dest


def repo_display_name(folder: str | Path) -> str:
    return Path(folder).expanduser().resolve().name or str(folder)
