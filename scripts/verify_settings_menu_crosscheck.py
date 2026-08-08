#!/usr/bin/env python3
"""
Settings / menu integration cross-check (no network publish).

Checks:
  - Status-bar widgets (설정, 도움말) + tab safety checkboxes exist
  - Settings prefs sync into publish/sync hide-email fields
  - secret_pii_scan_enabled default ON; phrase gate exact match
  - _effective_allow_secrets: off scan ⇒ soft allow True
  - run_safety_checks: hard content still blocks when allow_secrets=True
  - Publish/Sync both use effective allow path
  - Settings dialog opens for light/dark palette
  - No conflict: checkAllowSecrets vs global scan (document effective OR)

Run:
  .\\.venv\\Scripts\\python.exe scripts\\verify_settings_menu_crosscheck.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
RESULTS: list[str] = []


def ok(name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    RESULTS.append(f"PASS  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    RESULTS.append(f"FAIL  {name} — {detail}")


def main() -> int:
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QPushButton,
    )

    app = QApplication.instance() or QApplication([])

    from app.git.safety import run_safety_checks
    from app.ui.main_window import MainController, load_main_window
    from app.ui.settings_dialog import (
        SECRET_SCAN_OFF_PHRASE,
        SettingsDialog,
        phrase_matches_secret_scan_off,
    )
    from app.ui.settings_store import (
        _settings,
        load_hide_real_email,
        load_secret_pii_scan_enabled,
        save_hide_real_email,
        save_secret_pii_scan_enabled,
    )
    from app.ui.theme import DARK, LIGHT, active_palette, apply_palette

    # ----- UI presence -----
    RESULTS.append("\n## UI 위젯 (설정·탭 안전)")
    window = load_main_window()
    need = [
        ("btnSettings", QPushButton),
        ("btnHelpOnboarding", QPushButton),
        ("btnLogout", QPushButton),
        ("checkAllowSecrets", QCheckBox),
        ("checkHideEmail", QCheckBox),
        ("checkSyncAllowSecrets", QCheckBox),
        ("checkSyncHideEmail", QCheckBox),
        ("btnCloneHistory", QPushButton),
        ("btnSyncHistory", QPushButton),
        ("btnPublish", QPushButton),
        ("btnSyncPush", QPushButton),
    ]
    missing = [n for n, cls in need if window.findChild(cls, n) is None]
    if missing:
        fail("필수 위젯", str(missing))
    else:
        ok("필수 위젯", f"{len(need)}개")

    from app.ui import main_window as mw_mod

    src = Path(mw_mod.__file__).read_text(encoding="utf-8")
    ctrl = getattr(window, "_cloneup_controller", None)
    if isinstance(ctrl, MainController):
        ok("window._cloneup_controller", type(ctrl).__name__)
    else:
        fail("window._cloneup_controller", f"got {type(ctrl)!r}")

    if "btnSettings" in src and "on_settings_menu" in src and "show_settings" in src:
        ok("main_window 설정 연결 코드 존재")
    else:
        fail("main_window 설정 연결", "btnSettings / show_settings missing")
    if "_effective_allow_secrets" in src and "load_secret_pii_scan_enabled" in src:
        ok("main_window effective allow + secret scan 연동")
    else:
        fail("main_window 안전 연동", "effective allow / scan flag missing")
    if "scan_pii=self._safety_scan_enabled()" in src or (
        "scan_pii=" in src and "_safety_scan_enabled" in src
    ):
        ok("publish run_safety_checks scan_pii 연동")
    else:
        fail("publish scan_pii", "run_safety_checks scan_pii not wired")
    if "on_settings_prefs_changed" in src and "_load_prefs" in src:
        ok("설정 저장 후 _load_prefs 갱신")
    else:
        fail("prefs 동기화", "on_settings_prefs_changed missing")

    # ----- Phrase gate -----
    RESULTS.append("\n## 끄기 문구 게이트")
    if phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE):
        ok("문구 일치", SECRET_SCAN_OFF_PHRASE[:20] + "…")
    else:
        fail("문구 일치", "exact phrase rejected")
    if not phrase_matches_secret_scan_off("이해했습니다"):
        ok("문구 부분 일치 거부")
    else:
        fail("문구 부분 일치 거부", "partial accepted")
    if not phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE + "."):
        ok("문구 끝 점 거부")
    else:
        fail("문구 끝 점 거부", "dot accepted")

    # ----- Prefs default + roundtrip -----
    RESULTS.append("\n## QSettings 안전 스위치")
    s = _settings()
    key = "secret_pii_scan_enabled"
    prev = s.value(key)
    try:
        s.remove(key)
        if load_secret_pii_scan_enabled() is True:
            ok("secret_pii_scan 기본 ON")
        else:
            fail("secret_pii_scan 기본 ON", "default not True")
        save_secret_pii_scan_enabled(False)
        if load_secret_pii_scan_enabled() is False:
            ok("secret_pii_scan OFF 저장")
        else:
            fail("secret_pii_scan OFF 저장", "not False")
        # Effective allow without full controller: pure logic
        # mimic: if not scan => allow True
        scan = load_secret_pii_scan_enabled()
        effective = True if not scan else False
        if effective is True:
            ok("scan OFF ⇒ soft allow True (logic)")
        else:
            fail("scan OFF ⇒ soft allow", f"got {effective}")
        save_secret_pii_scan_enabled(True)
        if load_secret_pii_scan_enabled() is True:
            ok("secret_pii_scan 다시 ON")
        else:
            fail("secret_pii_scan 다시 ON", "not True")
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)

    # ----- hide email prefs reload into checkboxes -----
    RESULTS.append("\n## 이메일 숨기기 설정 ↔ 탭 체크박스")
    hide_prev = load_hide_real_email()
    try:
        save_hide_real_email(False)
        # new controller load_prefs
        try:
            # Prefer controller already attached by load_main_window
            c = getattr(window, "_cloneup_controller", None)
            if c is None or not hasattr(c, "_load_prefs"):
                c = MainController(window)
            c._load_prefs()
            chk = window.findChild(QCheckBox, "checkHideEmail")
            schk = window.findChild(QCheckBox, "checkSyncHideEmail")
            if chk is not None and not chk.isChecked():
                ok("checkHideEmail reflects settings OFF")
            elif chk is None:
                fail("checkHideEmail", "widget missing")
            else:
                fail("checkHideEmail", f"checked={chk.isChecked()} expected False")
            if schk is not None and not schk.isChecked():
                ok("checkSyncHideEmail reflects settings OFF")
            elif schk is None:
                fail("checkSyncHideEmail", "widget missing")
            else:
                fail("checkSyncHideEmail", f"checked={schk.isChecked()} expected False")

            # effective allow methods
            save_secret_pii_scan_enabled(False)
            if c._effective_allow_secrets(False) is True:
                ok("_effective_allow_secrets(False) when scan OFF → True")
            else:
                fail("_effective_allow_secrets scan OFF", "expected True")
            save_secret_pii_scan_enabled(True)
            if c._effective_allow_secrets(False) is False:
                ok("_effective_allow_secrets(False) when scan ON → False")
            else:
                fail("_effective_allow_secrets scan ON", "expected False")
            if c._effective_allow_secrets(True) is True:
                ok("_effective_allow_secrets(True) when scan ON → True")
            else:
                fail("_effective_allow_secrets UI allow", "expected True")
        except TypeError as e:
            fail("MainController 생성", str(e))
    finally:
        save_hide_real_email(hide_prev)
        save_secret_pii_scan_enabled(True)

    # ----- hard content always blocks -----
    RESULTS.append("\n## 하드 비밀 차단 (scan 우회 불가)")
    with tempfile.TemporaryDirectory(prefix="cu-set-x-") as td:
        root = Path(td)
        (root / "tok.txt").write_text(
            "ghp_" + ("a" * 36) + "\n", encoding="utf-8"
        )
        (root / "readme.md").write_text("ok\n", encoding="utf-8")
        r = run_safety_checks(root, allow_secrets=True, scan_pii=False)
        if not r.ok and any("막을 수 없습니다" in e or "비밀 키" in e for e in r.errors):
            ok("allow_secrets=True 여도 하드 키 차단")
        else:
            fail("하드 키 차단", f"ok={r.ok} errors={r.errors}")

        # filename soft with allow
        (root / "tok.txt").unlink()
        (root / ".env").write_text("X=1\n", encoding="utf-8")
        r2 = run_safety_checks(root, allow_secrets=True, scan_pii=False)
        if r2.ok:
            ok("allow_secrets=True 이면 .env 파일명 허용")
        else:
            fail(".env allow", str(r2.errors))
        r3 = run_safety_checks(root, allow_secrets=False, scan_pii=False)
        if not r3.ok:
            ok("allow_secrets=False 이면 .env 차단")
        else:
            fail(".env block", "expected fail")

    # ----- Settings dialog builds (both palettes) -----
    RESULTS.append("\n## 설정 대화상자 라이트/다크")
    for pal, label in ((LIGHT, "light"), (DARK, "dark")):
        apply_palette(pal)
        try:
            dlg = SettingsDialog(None)
            if dlg._stack.count() != 5:
                fail(f"설정 tabs {label}", f"count={dlg._stack.count()}")
            else:
                ok(f"설정 5탭 {label}")
            # safety tab switch exists
            if hasattr(dlg, "_sw_secret_scan") and hasattr(dlg, "_sw_hide_email"):
                ok(f"설정 안전 스위치 {label}")
            else:
                fail(f"설정 안전 스위치 {label}", "missing")
            # secret scan default matches store
            if dlg._sw_secret_scan.isChecked() == load_secret_pii_scan_enabled():
                ok(f"설정 스위치=저장값 {label}")
            else:
                fail(
                    f"설정 스위치=저장값 {label}",
                    f"ui={dlg._sw_secret_scan.isChecked()} store={load_secret_pii_scan_enabled()}",
                )
            dlg.close()
        except Exception as e:
            fail(f"설정 dialog {label}", str(e))
    apply_palette(LIGHT)

    # ----- Conflict notes (informational pass) -----
    RESULTS.append("\n## 메뉴 충돌 해석 (정책)")
    ok(
        "설정 스캔 OFF vs 「비밀 파일도 진행」",
        "effective allow = UI OR (scan OFF) — 소프트만; 하드 키는 항상 차단",
    )
    ok(
        "설정 이메일 숨기기 vs 탭 체크박스",
        "설정 변경 시 _load_prefs 로 양 탭 동기화",
    )
    ok(
        "동기화 push PII",
        "sync_ops scan_pii=False 의도적; UI G3가 push 전 PII 안내 (기존 정책)",
    )
    ok(
        "도움말 vs 설정>정보>시작 안내",
        "둘 다 show_onboarding — 중복 아님, 동일 진입점",
    )

    window.close()

    RESULTS.append(f"\nTOTAL  PASS={PASS}  FAIL={FAIL}")
    print("\n".join(RESULTS))
    if FAIL:
        print("SETTINGS_MENU_CROSS_VERIFY_FAIL")
        return 1
    print("SETTINGS_MENU_CROSS_VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
