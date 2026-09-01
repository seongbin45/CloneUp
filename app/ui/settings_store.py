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


# --- Boot / tray: unpushed-changes notify ---------------------------------


def load_boot_notify_enabled() -> bool:
    """Default True: check recent folders after logon (tray)."""
    return bool(_settings().value("boot_notify_enabled", True, type=bool))


def save_boot_notify_enabled(enabled: bool) -> None:
    _settings().setValue("boot_notify_enabled", bool(enabled))


def load_boot_notify_snooze_until() -> str | None:
    """ISO date ``YYYY-MM-DD`` until which boot notify is quiet, or None."""
    val = _settings().value("boot_notify_snooze_until", "")
    s = str(val).strip() if val else ""
    return s or None


def save_boot_notify_snooze_until(day: str | None) -> None:
    if day and str(day).strip():
        _settings().setValue("boot_notify_snooze_until", str(day).strip())
    else:
        _settings().remove("boot_notify_snooze_until")


def load_boot_notify_last_ask_day() -> str | None:
    """
    Day the user already acted on a boot toast (upload / dismiss-for-today).

    ``나중에`` does **not** set this — same-day reboot may ask again.
    """
    val = _settings().value("boot_notify_last_ask_day", "")
    s = str(val).strip() if val else ""
    return s or None


def save_boot_notify_last_ask_day(day: str | None) -> None:
    if day and str(day).strip():
        _settings().setValue("boot_notify_last_ask_day", str(day).strip())
    else:
        _settings().remove("boot_notify_last_ask_day")


def migrate_boot_notify_later_policy() -> None:
    """
    One-shot: old builds stamped last_ask on toast *show*, blocking same-day
    reboot after 「나중에». Clear that stamp once under policy v2.
    """
    if bool(_settings().value("boot_notify_later_policy_v2", False, type=bool)):
        return
    _settings().remove("boot_notify_last_ask_day")
    _settings().setValue("boot_notify_later_policy_v2", True)


def load_boot_autostart_enabled() -> bool:
    """Whether user wants CloneUp --tray in Windows startup."""
    return bool(_settings().value("boot_autostart_enabled", True, type=bool))


def save_boot_autostart_enabled(enabled: bool) -> None:
    _settings().setValue("boot_autostart_enabled", bool(enabled))


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


def load_history_revert_enabled() -> bool:
    """
    Default False: 커밋 내역 stays 읽기 전용 until the user opts in.

    Chosen once in first-run onboarding (skippable — this default is what
    skip-through users get); changeable any time in Settings > 안전.
    True unlocks 지워지지 않습니다 mode: a revert button that stacks a new
    commit restoring old content (nothing is ever erased).
    """
    return bool(_settings().value("history_revert_enabled", False, type=bool))


def save_history_revert_enabled(enabled: bool) -> None:
    _settings().setValue("history_revert_enabled", bool(enabled))


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


# ----- user glossary (설정 → 용어 안내) -----
# Built-in GLOSSARY_ENTRIES stay in code; these are user-added extras only.
# No practical count cap — terms are short and local-only. Field lengths only.
USER_GLOSSARY_TERM_MAX = 40
USER_GLOSSARY_LINE_MAX = 80
USER_GLOSSARY_DETAIL_MAX = 400


def load_user_glossary() -> list[tuple[str, str, str]]:
    """Return user-defined (term, one_line, detail) rows from QSettings."""
    raw = _settings().value("user_glossary_entries", [])
    if raw is None:
        return []
    if isinstance(raw, str):
        # Unexpected single string — ignore
        return []
    out: list[tuple[str, str, str]] = []
    try:
        items = list(raw)
    except TypeError:
        return []
    for item in items:
        term, one, detail = "", "", ""
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            term = str(item[0] or "").strip()
            one = str(item[1] or "").strip()
            detail = str(item[2] or "").strip() if len(item) >= 3 else ""
        elif isinstance(item, dict):
            term = str(item.get("term") or item.get("t") or "").strip()
            one = str(item.get("one_line") or item.get("summary") or item.get("s") or "").strip()
            detail = str(item.get("detail") or item.get("d") or "").strip()
        else:
            continue
        if not term or not one:
            continue
        out.append(
            (
                term[:USER_GLOSSARY_TERM_MAX],
                one[:USER_GLOSSARY_LINE_MAX],
                detail[:USER_GLOSSARY_DETAIL_MAX],
            )
        )
    return out


def save_user_glossary(entries: list[tuple[str, str, str]]) -> None:
    """Persist user glossary (overwrites). Built-in terms are never stored here."""
    cleaned: list[list[str]] = []
    for term, one, detail in entries:
        t = (term or "").strip()[:USER_GLOSSARY_TERM_MAX]
        o = (one or "").strip()[:USER_GLOSSARY_LINE_MAX]
        d = (detail or "").strip()[:USER_GLOSSARY_DETAIL_MAX]
        if not t or not o:
            continue
        cleaned.append([t, o, d])
    _settings().setValue("user_glossary_entries", cleaned)


def add_user_glossary_entry(term: str, one_line: str, detail: str = "") -> bool:
    """
    Append one user term. Returns False if empty or duplicate term name
    (case-insensitive, against existing user entries only).
    """
    t = (term or "").strip()[:USER_GLOSSARY_TERM_MAX]
    o = (one_line or "").strip()[:USER_GLOSSARY_LINE_MAX]
    d = (detail or "").strip()[:USER_GLOSSARY_DETAIL_MAX]
    if not t or not o:
        return False
    cur = load_user_glossary()
    low = t.casefold()
    if any(x[0].casefold() == low for x in cur):
        return False
    cur.append((t, o, d))
    save_user_glossary(cur)
    return True


def remove_user_glossary_entry(term: str) -> bool:
    """Remove first user entry whose term matches (case-insensitive)."""
    t = (term or "").strip()
    if not t:
        return False
    low = t.casefold()
    cur = load_user_glossary()
    nxt = [x for x in cur if x[0].casefold() != low]
    if len(nxt) == len(cur):
        return False
    save_user_glossary(nxt)
    return True
