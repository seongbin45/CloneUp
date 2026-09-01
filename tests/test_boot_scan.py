"""Boot notify scan helpers (no live git required for parse/quiet)."""

from __future__ import annotations

from app.ui.boot_scan import (
    boot_notify_is_quiet,
    folder_needs_notify,
    parse_porcelain_line,
    snooze_until_days,
)


def test_parse_porcelain_kinds() -> None:
    m = parse_porcelain_line(" M app/ui/main_window.py")
    assert m is not None and m.kind == "M"
    assert m.path.endswith("main_window.py")
    a = parse_porcelain_line("A  app/ui/boot_notify.py")
    assert a is not None and a.kind == "A"
    d = parse_porcelain_line("D  old.txt")
    assert d is not None and d.kind == "D"
    u = parse_porcelain_line("?? scratch.tmp")
    assert u is not None and u.kind == "?"
    assert parse_porcelain_line("") is None


def test_folder_needs_notify_rules() -> None:
    class St:
        def __init__(self, dirty=False, ahead=None, conflict=False):
            self.dirty = dirty
            self.ahead = ahead
            self.conflict = conflict

    assert folder_needs_notify(St(dirty=True)) is True
    assert folder_needs_notify(St(ahead=2)) is True
    assert folder_needs_notify(St()) is False
    assert folder_needs_notify(St(dirty=True, conflict=True)) is False


def test_quiet_prefs(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_enabled", lambda: True
    )
    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_snooze_until", lambda: "2099-01-01"
    )
    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_last_ask_day", lambda: None
    )
    assert boot_notify_is_quiet(today="2026-09-02") is True

    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_snooze_until", lambda: None
    )
    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_last_ask_day",
        lambda: "2026-09-02",
    )
    # After upload / disable — quiet for the rest of that day.
    assert boot_notify_is_quiet(today="2026-09-02") is True
    assert boot_notify_is_quiet(today="2026-09-03") is False

    monkeypatch.setattr(
        "app.ui.boot_scan.load_boot_notify_enabled", lambda: False
    )
    assert boot_notify_is_quiet(today="2026-09-03") is True


def test_clear_boot_notify_asked(monkeypatch) -> None:
    from app.ui.boot_scan import clear_boot_notify_asked, mark_boot_notify_asked

    stored: dict[str, str | None] = {"day": "2026-09-02"}

    monkeypatch.setattr(
        "app.ui.boot_scan.save_boot_notify_last_ask_day",
        lambda day: stored.__setitem__("day", day),
    )
    clear_boot_notify_asked()
    assert stored["day"] is None
    mark_boot_notify_asked(today="2026-09-02")
    assert stored["day"] == "2026-09-02"


def test_snooze_until_days_format() -> None:
    s = snooze_until_days(7)
    assert len(s) == 10 and s[4] == "-" and s[7] == "-"
