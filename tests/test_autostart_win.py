"""HKCU Run sync for boot tray autostart (no real registry required)."""

from __future__ import annotations


def test_apply_autostart_preference_reads_store(monkeypatch) -> None:
    calls: list[bool] = []

    monkeypatch.setattr(
        "app.ui.settings_store.load_boot_autostart_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.util.autostart_win.set_autostart_registered",
        lambda enabled: calls.append(bool(enabled)) or True,
    )

    from app.util.autostart_win import apply_autostart_preference

    assert apply_autostart_preference() is True
    assert calls == [True]


def test_apply_autostart_preference_explicit_off(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(
        "app.util.autostart_win.set_autostart_registered",
        lambda enabled: calls.append(bool(enabled)) or True,
    )
    from app.util.autostart_win import apply_autostart_preference

    assert apply_autostart_preference(False) is True
    assert calls == [False]


def test_set_autostart_registered_non_windows(monkeypatch) -> None:
    import app.util.autostart_win as m

    monkeypatch.setattr(m.sys, "platform", "linux")
    assert m.set_autostart_registered(True) is False
    assert m.is_autostart_registered() is False
