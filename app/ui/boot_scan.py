"""Scan recent folders for unpushed / dirty work (boot notify)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from app.ui.settings_store import (
    load_boot_notify_enabled,
    load_boot_notify_last_ask_day,
    load_boot_notify_snooze_until,
    load_recent_folders,
    save_boot_notify_last_ask_day,
)


@dataclass(frozen=True)
class ChangedFile:
    kind: str  # M / A / D / ?
    path: str
    tone: str  # hex for badge


@dataclass(frozen=True)
class PendingFolder:
    path: str
    name: str
    files: tuple[ChangedFile, ...]
    dirty: bool
    ahead: int
    file_count: int


_TONE_M = "#8a6d12"
_TONE_A = "#1f6f5c"
_TONE_D = "#a33b2b"
_TONE_Q = "#6d675c"


def today_iso() -> str:
    return date.today().isoformat()


def snooze_until_days(days: int = 7) -> str:
    return (date.today() + timedelta(days=max(0, int(days)))).isoformat()


def boot_notify_is_quiet(*, today: str | None = None) -> bool:
    """True when prefs say do not show a boot toast now."""
    if not load_boot_notify_enabled():
        return True
    day = today or today_iso()
    snooze = load_boot_notify_snooze_until()
    if snooze and snooze >= day:
        return True
    last = load_boot_notify_last_ask_day()
    if last and last == day:
        return True
    return False


def mark_boot_notify_asked(*, today: str | None = None) -> None:
    save_boot_notify_last_ask_day(today or today_iso())


def parse_porcelain_line(line: str) -> ChangedFile | None:
    """Map one ``git status --porcelain`` line to a ChangedFile."""
    raw = (line or "").rstrip("\n")
    if not raw.strip():
        return None
    # XY PATH or XY ORIG -> PATH
    if raw.startswith("??"):
        path = raw[2:].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        return ChangedFile(kind="?", path=path or "?", tone=_TONE_Q)
    if len(raw) < 4:
        return None
    xy = raw[:2]
    rest = raw[3:].strip()
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[-1].strip()
    if rest.startswith('"') and rest.endswith('"'):
        rest = rest[1:-1]
    # Prefer index status, else worktree
    ch = xy[0] if xy[0] != " " else xy[1]
    if ch in "AM":
        kind, tone = ("A" if ch == "A" else "M"), (_TONE_A if ch == "A" else _TONE_M)
    elif ch in "D":
        kind, tone = "D", _TONE_D
    elif ch in "RCSU":
        kind, tone = "M", _TONE_M
    elif ch == "?":
        kind, tone = "?", _TONE_Q
    else:
        kind, tone = "M", _TONE_M
    return ChangedFile(kind=kind, path=rest or "?", tone=tone)


def list_changed_files(folder: Path, *, limit: int = 3) -> list[ChangedFile]:
    from app.git.runner import run_git

    folder = folder.expanduser().resolve()
    st = run_git(["status", "--porcelain"], cwd=str(folder), check=False)
    if st.returncode != 0:
        return []
    out: list[ChangedFile] = []
    for ln in (st.stdout or "").splitlines():
        got = parse_porcelain_line(ln)
        if got is None:
            continue
        out.append(got)
        if len(out) >= max(1, int(limit)):
            break
    return out


def folder_needs_notify(status) -> bool:
    """Dirty working tree or local commits ahead of origin."""
    if getattr(status, "conflict", False):
        return False
    if getattr(status, "dirty", False):
        return True
    ahead = getattr(status, "ahead", None)
    return isinstance(ahead, int) and ahead > 0


def collect_pending(
    folders: list[str] | None = None,
    *,
    file_limit: int = 3,
) -> list[PendingFolder]:
    """Scan folders (default: recent) for upload-worthy changes."""
    from app.git.sync_ops import SyncError, get_repo_status

    paths = folders if folders is not None else load_recent_folders()
    pending: list[PendingFolder] = []
    for raw in paths:
        p = Path(raw).expanduser()
        try:
            p = p.resolve()
        except Exception:
            continue
        if not p.is_dir() or not (p / ".git").exists():
            continue
        try:
            st = get_repo_status(p)
        except SyncError:
            continue
        except Exception:
            continue
        if not folder_needs_notify(st):
            continue
        files = tuple(list_changed_files(p, limit=file_limit))
        # Count all porcelain lines for badge (best-effort)
        count = len(files)
        try:
            from app.git.runner import run_git

            full = run_git(["status", "--porcelain"], cwd=str(p), check=False)
            if full.returncode == 0:
                n = len([ln for ln in (full.stdout or "").splitlines() if ln.strip()])
                if n > 0:
                    count = n
        except Exception:
            pass
        if count == 0 and (st.ahead or 0) > 0:
            count = int(st.ahead or 0)
        pending.append(
            PendingFolder(
                path=str(p),
                name=p.name or str(p),
                files=files,
                dirty=bool(st.dirty),
                ahead=int(st.ahead or 0),
                file_count=max(count, len(files)),
            )
        )
    return pending


def should_show_boot_toast(
    pending: list[PendingFolder] | None = None,
    *,
    today: str | None = None,
) -> list[PendingFolder]:
    """Return pending list to show, or empty if quiet / nothing to do."""
    if boot_notify_is_quiet(today=today):
        return []
    items = pending if pending is not None else collect_pending()
    return list(items)
