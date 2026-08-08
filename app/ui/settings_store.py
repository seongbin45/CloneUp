"""Persist lightweight UI prefs (recent folders, last visibility)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

ORG = "CloneUp"
APP = "CloneUp"
MAX_RECENT = 12


def _settings() -> QSettings:
    return QSettings(ORG, APP)


def load_recent_folders() -> list[str]:
    raw = _settings().value("recent_folders", [])
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw] if raw else []
    else:
        items = [str(x) for x in raw]
    # keep existing dirs first
    out: list[str] = []
    for p in items:
        if p and p not in out:
            out.append(p)
    return out[:MAX_RECENT]


def remember_folder(folder: str) -> list[str]:
    path = str(Path(folder).expanduser().resolve())
    items = load_recent_folders()
    items = [path] + [x for x in items if x != path]
    items = items[:MAX_RECENT]
    _settings().setValue("recent_folders", items)
    return items


def clear_recent_folders() -> None:
    """Wipe the recent-folder list (settings menu)."""
    _settings().setValue("recent_folders", [])


def load_last_private() -> bool:
    """Default True: beginner-safe private repos (M5 / security review)."""
    return bool(_settings().value("last_private", True, type=bool))


def save_last_private(private: bool) -> None:
    _settings().setValue("last_private", bool(private))


def load_last_commit_message() -> str:
    val = _settings().value("last_commit_message", "첫 업로드")
    s = str(val) if val else "첫 업로드"
    # Migrate old English default for beginners
    if s.strip() in ("Initial commit", "initial commit"):
        return "첫 업로드"
    return s or "첫 업로드"


def save_last_commit_message(msg: str) -> None:
    if msg.strip():
        _settings().setValue("last_commit_message", msg.strip())


def load_last_github_login() -> str | None:
    val = _settings().value("last_github_login", "")
    s = str(val).strip() if val else ""
    return s or None


def save_last_github_login(login: str) -> None:
    if login.strip():
        _settings().setValue("last_github_login", login.strip())


def load_hide_real_email() -> bool:
    """Default True: beginner-safe hide school/work email in commits."""
    return bool(_settings().value("hide_real_email", True, type=bool))


def save_hide_real_email(hide: bool) -> None:
    _settings().setValue("hide_real_email", bool(hide))


def load_secret_pii_scan_enabled() -> bool:
    """
    Default True: run secret-filename / soft content / PII checks before upload.

    When False (only after typed confirmation in Settings), soft checks are
    skipped. High-confidence content secrets (keys, PEM) still always block.
    """
    return bool(_settings().value("secret_pii_scan_enabled", True, type=bool))


def save_secret_pii_scan_enabled(enabled: bool) -> None:
    _settings().setValue("secret_pii_scan_enabled", bool(enabled))


def load_hard_revert_enabled() -> bool:
    """
    Default False (opt-in): offer "기록까지 지우고 되돌리기" in 커밋 내역.

    That path rewrites history (git reset --hard + force push) — more than
    the default "기록을 남기고 되돌리기", which stays available either way.
    """
    return bool(_settings().value("hard_revert_enabled", False, type=bool))


def save_hard_revert_enabled(enabled: bool) -> None:
    _settings().setValue("hard_revert_enabled", bool(enabled))


def load_last_publish_branch() -> str:
    """Default branch for first publish (usually main)."""
    val = _settings().value("last_publish_branch", "main")
    s = str(val).strip() if val else "main"
    return s or "main"


def save_last_publish_branch(branch: str) -> None:
    b = (branch or "").strip()
    if b:
        _settings().setValue("last_publish_branch", b)


def load_onboarding_done() -> bool:
    """True after first-run wizard completed (or skipped to finish)."""
    return bool(_settings().value("onboarding_done", False, type=bool))


def save_onboarding_done(done: bool = True) -> None:
    _settings().setValue("onboarding_done", bool(done))
