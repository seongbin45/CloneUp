"""Phase A: main shell mode resolve (home vs legacy)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ini = tmp_path / "cloneup_test.ini"

    def _factory() -> QSettings:
        return QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr("app.ui.settings_store._settings", _factory)
    monkeypatch.delenv("CLONEUP_LEGACY_TABS", raising=False)
    return ini


def test_new_install_seeds_home(isolated_settings) -> None:
    from app.ui.ui_mode import resolve_main_shell
    from app.ui.settings_store import load_main_shell_raw, load_home_offer_pending

    assert resolve_main_shell() == "home"
    assert load_main_shell_raw() == "home"
    assert load_home_offer_pending() is False


def test_existing_install_seeds_legacy_with_offer(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ui import settings_store as ss
    from app.ui.ui_mode import resolve_main_shell

    ss._settings().setValue("recent_folders", [r"C:\fake\proj"])
    assert resolve_main_shell() == "legacy"
    assert ss.load_main_shell_raw() == "legacy"
    assert ss.load_home_offer_pending() is True


def test_explicit_home_and_legacy(isolated_settings) -> None:
    from app.ui.settings_store import save_main_shell, load_main_shell_raw
    from app.ui.ui_mode import resolve_main_shell

    save_main_shell("home")
    assert resolve_main_shell() == "home"
    save_main_shell("legacy")
    assert resolve_main_shell() == "legacy"
    assert load_main_shell_raw() == "legacy"


def test_banana_corrects_to_home(isolated_settings) -> None:
    from app.ui.settings_store import _settings, load_main_shell_raw
    from app.ui.ui_mode import resolve_main_shell

    _settings().setValue("ui/main_shell", "banana")
    assert resolve_main_shell() == "home"
    assert load_main_shell_raw() == "home"


def test_env_truthy_overrides_home(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ui.settings_store import save_main_shell
    from app.ui.ui_mode import resolve_main_shell, use_legacy_tabs

    save_main_shell("home")
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "1")
    assert resolve_main_shell() == "legacy"
    assert use_legacy_tabs() is True


def test_env_falsy_overrides_legacy(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ui.settings_store import save_main_shell
    from app.ui.ui_mode import resolve_main_shell, use_legacy_tabs

    save_main_shell("legacy")
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "0")
    assert resolve_main_shell() == "home"
    assert use_legacy_tabs() is False


def test_env_banana_ignored(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ui.settings_store import save_main_shell
    from app.ui.ui_mode import parse_legacy_tabs_env, resolve_main_shell

    save_main_shell("legacy")
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "banana")
    assert parse_legacy_tabs_env() is None
    assert resolve_main_shell() == "legacy"


def test_env_unset_uses_settings(isolated_settings) -> None:
    from app.ui.settings_store import save_main_shell
    from app.ui.ui_mode import resolve_main_shell

    save_main_shell("legacy")
    assert resolve_main_shell() == "legacy"


def test_roundtrip(isolated_settings) -> None:
    from app.ui.settings_store import save_main_shell, load_main_shell_raw
    from app.ui.ui_mode import resolve_main_shell

    save_main_shell("home")
    assert load_main_shell_raw() == "home"
    assert resolve_main_shell() == "home"
    save_main_shell("legacy")
    assert resolve_main_shell() == "legacy"


def test_legacy_tabs_env_active(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ui.ui_mode import legacy_tabs_env_active

    assert legacy_tabs_env_active() is False
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "yes")
    assert legacy_tabs_env_active() is True
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "banana")
    assert legacy_tabs_env_active() is False


def test_project_scan_use_legacy_tabs_delegates(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.git.project_scan import use_legacy_tabs
    from app.ui.settings_store import save_main_shell

    save_main_shell("home")
    monkeypatch.delenv("CLONEUP_LEGACY_TABS", raising=False)
    assert use_legacy_tabs() is False
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "true")
    assert use_legacy_tabs() is True
