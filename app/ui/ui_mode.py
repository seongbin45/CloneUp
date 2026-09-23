"""Main UI shell mode: home vs legacy tabs (plan rev.4).

Settings key ``ui/main_shell``; env ``CLONEUP_LEGACY_TABS`` overrides (U-3b).
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from app.ui.settings_store import (
    MAIN_SHELL_HOME,
    MAIN_SHELL_LEGACY,
    has_existing_install_trace,
    load_home_offer_pending,
    load_main_shell_raw,
    save_home_offer_pending,
    save_main_shell,
)

MainShell = Literal["home", "legacy"]

_log = logging.getLogger(__name__)

_ENV_TRUTHY = frozenset({"1", "true", "yes", "on"})
_ENV_FALSY = frozenset({"0", "false", "no", "off"})


def parse_legacy_tabs_env(
    raw: str | None = None,
) -> Literal["legacy", "home"] | None:
    """Parse CLONEUP_LEGACY_TABS. None = env absent or ignored (banana)."""
    if raw is None:
        raw = os.environ.get("CLONEUP_LEGACY_TABS")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in _ENV_TRUTHY:
        return MAIN_SHELL_LEGACY
    if text in _ENV_FALSY:
        return MAIN_SHELL_HOME
    # U-3b: garbage → ignore env
    return None


def legacy_tabs_env_active() -> bool:
    """True when env forces a shell mode (settings UI should lock)."""
    return parse_legacy_tabs_env() is not None


def _normalize_stored(raw: str | None) -> MainShell | None:
    if raw is None:
        return None
    if raw in (MAIN_SHELL_HOME, MAIN_SHELL_LEGACY):
        return raw  # type: ignore[return-value]
    return None


def seed_main_shell_if_needed() -> MainShell:
    """U-1b: write initial ui/main_shell when the key is missing."""
    existing = _normalize_stored(load_main_shell_raw())
    if existing is not None:
        return existing
    if has_existing_install_trace():
        save_main_shell(MAIN_SHELL_LEGACY)
        save_home_offer_pending(True)
        _log.info(
            "ui/main_shell seeded to legacy (existing install) + home offer pending"
        )
        return MAIN_SHELL_LEGACY
    save_main_shell(MAIN_SHELL_HOME)
    save_home_offer_pending(False)
    _log.info("ui/main_shell seeded to home (new install)")
    return MAIN_SHELL_HOME


def resolve_main_shell() -> MainShell:
    """Effective shell mode: env override → else settings (with U-1b seed)."""
    forced = parse_legacy_tabs_env()
    if forced is not None:
        return forced

    raw = load_main_shell_raw()
    normalized = _normalize_stored(raw)
    if normalized is not None:
        return normalized
    if raw is not None:
        # Corrupt value — correct to home (plan: banana → home + log)
        _log.warning(
            "ui/main_shell corrupt value %r — correcting to home", raw
        )
        return save_main_shell(MAIN_SHELL_HOME)  # type: ignore[return-value]
    return seed_main_shell_if_needed()


def use_legacy_tabs() -> bool:
    """True when the legacy tab main should be the only shell."""
    return resolve_main_shell() == MAIN_SHELL_LEGACY


def maybe_offer_home_shell(parent=None) -> bool:
    """U-1b: one-shot offer after legacy seed (Phase B).

    Call after the main window is shown. Priority note: prefer not to stack
    on top of blocking onboarding; Git-missing banner is non-modal so OK.

    Returns True if the user chose home (caller should hint restart).
    """
    if legacy_tabs_env_active():
        return False
    if not load_home_offer_pending():
        return False
    # Only meaningful while legacy is the effective mode
    if resolve_main_shell() != MAIN_SHELL_LEGACY:
        save_home_offer_pending(False)
        return False

    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setWindowTitle("새 홈 화면")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(
        "폴더를 먼저 고르는 새 홈 화면을 써보시겠습니까?\n\n"
        "나중에 설정 → 화면에서도 바꿀 수 있습니다."
    )
    yes = box.addButton("홈 화면 쓰기", QMessageBox.ButtonRole.YesRole)
    later = box.addButton("나중에", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(later)
    box.exec()
    clicked = box.clickedButton()
    save_home_offer_pending(False)
    if clicked is yes:
        save_main_shell(MAIN_SHELL_HOME)
        QMessageBox.information(
            parent,
            "새 홈 화면",
            "홈 화면으로 설정했습니다.\n"
            "적용하려면 클론업을 종료한 뒤 다시 열어 주세요.",
        )
        return True
    return False
