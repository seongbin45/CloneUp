#!/usr/bin/env python3
"""
Step-by-step cross-check: 설정 dialog ↔ main tabs (만들기/받기/동기화).

Does not open the modal interactively; drives store + controller apply paths
the same way the live UI does after each settings auto-save.

Steps:
  S1  올리기 기본값 · 공개 범위 → radioPrivate / radioPublic
  S2  올리기 기본값 · 첫 커밋 메시지 → editCommitMessage
  S3  올리기 기본값 · 기본 브랜치 → comboPublishBranch
  S4  안전 · 이메일 숨기기 → checkHideEmail + checkSyncHideEmail
  S5  안전 · 이메일 변경이 커밋 메시지를 덮지 않음 (회귀)
  S6  최근 폴더 비우기 → 만들기/동기화 최근 폴더 드롭다운(QCompleter)
  S7  비밀·개인정보 점검 OFF → _effective_allow_secrets
  S8  설정 저장값이 만들기 탭 위젯과 일치 (S1–S3 재확인)
  S9  동기화 탭 이메일 체크 = 만들기 탭 이메일 체크
  S10 secret_scan 은 탭 위젯 없음 · load 경로만

Run:
  .\\.venv\\Scripts\\python.exe scripts\\verify_settings_tabs_sync.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
RESULTS: list[str] = []


def ok(step: str, name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    RESULTS.append(f"PASS  [{step}] {name}" + (f" — {detail}" if detail else ""))


def fail(step: str, name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    RESULTS.append(f"FAIL  [{step}] {name} — {detail}")


def main() -> int:
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QLineEdit,
        QRadioButton,
    )

    app = QApplication.instance() or QApplication([])

    from app.ui.main_window import load_main_window
    from app.ui.settings_store import (
        _settings,
        clear_recent_folders,
        load_hide_real_email,
        load_last_commit_message,
        load_last_private,
        load_last_publish_branch,
        load_recent_folders,
        load_secret_pii_scan_enabled,
        remember_folder,
        save_hide_real_email,
        save_last_commit_message,
        save_last_private,
        save_last_publish_branch,
        save_secret_pii_scan_enabled,
    )

    # Snapshot prefs to restore
    snap = {
        "private": load_last_private(),
        "msg": load_last_commit_message(),
        "branch": load_last_publish_branch(),
        "hide": load_hide_real_email(),
        "scan": load_secret_pii_scan_enabled(),
        "recent": list(load_recent_folders()),
    }

    window = load_main_window()
    ctrl = getattr(window, "_cloneup_controller", None)
    if ctrl is None:
        fail("0", "controller", "window._cloneup_controller missing")
        print("\n".join(RESULTS))
        return 1
    ok("0", "MainController 연결")

    def w(name: str, cls):
        return window.findChild(cls, name)

    radio_priv = w("radioPrivate", QRadioButton)
    radio_pub = w("radioPublic", QRadioButton)
    edit_msg = w("editCommitMessage", QLineEdit)
    combo_br = w("comboPublishBranch", QComboBox)
    chk_hide = w("checkHideEmail", QCheckBox)
    chk_sync_hide = w("checkSyncHideEmail", QCheckBox)

    for label, obj in [
        ("radioPrivate", radio_priv),
        ("radioPublic", radio_pub),
        ("editCommitMessage", edit_msg),
        ("comboPublishBranch", combo_br),
        ("checkHideEmail", chk_hide),
        ("checkSyncHideEmail", chk_sync_hide),
    ]:
        if obj is None:
            fail("0", f"위젯 {label}", "없음")
        else:
            ok("0", f"위젯 {label}")

    try:
        # ----- S1 private -----
        RESULTS.append("\n## S1 공개 범위 → 만들고 올리기")
        save_last_private(True)
        ctrl._apply_settings_store_to_tabs("private")
        if radio_priv is not None and radio_priv.isChecked():
            ok("S1", "비공개 설정 → radioPrivate 선택")
        else:
            fail("S1", "비공개", f"priv={radio_priv.isChecked() if radio_priv else None}")
        save_last_private(False)
        ctrl._apply_settings_store_to_tabs("private")
        if radio_pub is not None and radio_pub.isChecked():
            ok("S1", "공개 설정 → radioPublic 선택")
        else:
            fail("S1", "공개", f"pub={radio_pub.isChecked() if radio_pub else None}")
        if load_last_private() is False:
            ok("S1", "store last_private=False")
        else:
            fail("S1", "store", "last_private still True")

        # ----- S2 message -----
        RESULTS.append("\n## S2 첫 커밋 메시지 → 만들고 올리기")
        marker = "교차검증-커밋메시지-XYZ"
        save_last_commit_message(marker)
        ctrl._apply_settings_store_to_tabs("message")
        got = (edit_msg.text() if edit_msg else "")
        if got == marker:
            ok("S2", "editCommitMessage 동기화", marker)
        else:
            fail("S2", "editCommitMessage", f"got {got!r}")

        # ----- S3 branch -----
        RESULTS.append("\n## S3 기본 브랜치 → 만들고 올리기")
        br_marker = "cross-verify-branch"
        save_last_publish_branch(br_marker)
        ctrl._apply_settings_store_to_tabs("branch")
        got_br = (combo_br.currentText() if combo_br else "")
        if got_br == br_marker:
            ok("S3", "comboPublishBranch 동기화", br_marker)
        else:
            fail("S3", "comboPublishBranch", f"got {got_br!r}")

        # ----- S4 hide email both tabs -----
        RESULTS.append("\n## S4 이메일 숨기기 → 만들기 + 동기화")
        save_hide_real_email(False)
        ctrl._apply_settings_store_to_tabs("hide_email")
        if chk_hide is not None and not chk_hide.isChecked():
            ok("S4", "checkHideEmail OFF")
        else:
            fail("S4", "checkHideEmail", f"{chk_hide.isChecked() if chk_hide else None}")
        if chk_sync_hide is not None and not chk_sync_hide.isChecked():
            ok("S4", "checkSyncHideEmail OFF")
        else:
            fail(
                "S4",
                "checkSyncHideEmail",
                f"{chk_sync_hide.isChecked() if chk_sync_hide else None}",
            )
        save_hide_real_email(True)
        ctrl._apply_settings_store_to_tabs("hide_email")
        if (
            chk_hide is not None
            and chk_hide.isChecked()
            and chk_sync_hide is not None
            and chk_sync_hide.isChecked()
        ):
            ok("S4", "양쪽 탭 ON 동기화")
        else:
            fail("S4", "양쪽 ON", "mismatch")

        # ----- S5 hide_email must not clobber message -----
        RESULTS.append("\n## S5 안전 변경이 올리기 메시지를 덮지 않음")
        if edit_msg is not None:
            edit_msg.setText("작업중-덮이면안됨")
        save_hide_real_email(False)
        ctrl._apply_settings_store_to_tabs("hide_email")
        still = edit_msg.text() if edit_msg else ""
        if still == "작업중-덮이면안됨":
            ok("S5", "hide_email apply 후 메시지 유지")
        else:
            fail("S5", "메시지 덮임", f"got {still!r}")
        # branch should also survive
        if combo_br is not None:
            combo_br.setEditText("keep-branch-please")
        ctrl._apply_settings_store_to_tabs("hide_email")
        if combo_br is not None and combo_br.currentText() == "keep-branch-please":
            ok("S5", "hide_email apply 후 브랜치 유지")
        else:
            fail(
                "S5",
                "브랜치 덮임",
                f"got {combo_br.currentText() if combo_br else None!r}",
            )

        # ----- S6 recent clear -----
        RESULTS.append("\n## S6 최근 폴더 → 만들기/동기화 드롭다운")
        fake = str(Path.home() / "CloneUpCrossVerifyFake")
        remember_folder(fake)
        ctrl._apply_settings_store_to_tabs("recent")
        texts_p = ctrl._recentPopupPublish.items()
        texts_s = ctrl._recentPopupSync.items()
        if fake in texts_p and fake in texts_s:
            ok("S6", "remember_folder → 양쪽 드롭다운 반영")
        else:
            fail("S6", "remember 반영", f"pub={texts_p} sync={texts_s}")
        clear_recent_folders()
        ctrl._apply_settings_store_to_tabs("recent")
        texts_p2 = ctrl._recentPopupPublish.items()
        texts_s2 = ctrl._recentPopupSync.items()
        if fake not in texts_p2 and fake not in texts_s2:
            ok("S6", "목록 비우기 → 양쪽 드롭다운에서 제거")
        else:
            fail("S6", "비우기", f"pub={texts_p2} sync={texts_s2}")
        if texts_p2 == texts_s2:
            ok("S6", "만들기 드롭다운 == 동기화 드롭다운")
        else:
            fail("S6", "드롭다운 불일치", f"{texts_p2} vs {texts_s2}")

        # ----- S7 secret scan effective allow -----
        RESULTS.append("\n## S7 비밀·개인정보 점검 → 올리기/동기화 유효 허용")
        save_secret_pii_scan_enabled(True)
        if ctrl._effective_allow_secrets(False) is False:
            ok("S7", "scan ON + UI 미허용 → effective False")
        else:
            fail("S7", "scan ON", "expected False")
        save_secret_pii_scan_enabled(False)
        ctrl._apply_settings_store_to_tabs("secret_scan")  # no widget; no crash
        if ctrl._effective_allow_secrets(False) is True:
            ok("S7", "scan OFF → effective True (소프트 우회)")
        else:
            fail("S7", "scan OFF", "expected True")
        if ctrl._safety_scan_enabled() is False:
            ok("S7", "load_secret_pii_scan_enabled 반영")
        else:
            fail("S7", "scan flag", "still True")
        save_secret_pii_scan_enabled(True)

        # ----- S8 defaults roundtrip via apply all -----
        RESULTS.append("\n## S8 기본값 일괄 apply('all')")
        save_last_private(True)
        save_last_commit_message("일괄-메시지")
        save_last_publish_branch("main")
        ctrl._apply_settings_store_to_tabs("all")
        if radio_priv is not None and radio_priv.isChecked():
            ok("S8", "all → private")
        else:
            fail("S8", "all private", "not checked")
        if edit_msg is not None and edit_msg.text() == "일괄-메시지":
            ok("S8", "all → message")
        else:
            fail("S8", "all message", repr(edit_msg.text() if edit_msg else None))
        if combo_br is not None and (combo_br.currentText() or "") == "main":
            ok("S8", "all → branch main")
        else:
            fail("S8", "all branch", repr(combo_br.currentText() if combo_br else None))

        # ----- S9 publish hide == sync hide -----
        RESULTS.append("\n## S9 만들기 이메일 체크 == 동기화 이메일 체크")
        save_hide_real_email(False)
        ctrl._apply_settings_store_to_tabs("hide_email")
        if chk_hide is not None and chk_sync_hide is not None:
            if chk_hide.isChecked() == chk_sync_hide.isChecked() is False:
                ok("S9", "양쪽 False 동일")
            else:
                fail(
                    "S9",
                    "불일치",
                    f"pub={chk_hide.isChecked()} sync={chk_sync_hide.isChecked()}",
                )
        save_hide_real_email(True)
        ctrl._apply_settings_store_to_tabs("hide_email")
        if chk_hide is not None and chk_sync_hide is not None:
            if chk_hide.isChecked() and chk_sync_hide.isChecked():
                ok("S9", "양쪽 True 동일")
            else:
                fail("S9", "True 불일치", "")

        # ----- S10 receive tab not broken by settings apply -----
        RESULTS.append("\n## S10 받기 탭 필드 (설정 기본값과 무관)")
        # clone parent / url not in settings store — apply should not clear them
        edit_parent = w("editCloneParent", QLineEdit)
        if edit_parent is not None:
            edit_parent.setText(r"C:\Users\Public\CloneUpSyncTest")
            ctrl._apply_settings_store_to_tabs("all")
            if edit_parent.text() == r"C:\Users\Public\CloneUpSyncTest":
                ok("S10", "설정 apply 후 받기 저장 위치 유지")
            else:
                fail("S10", "받기 저장 위치 덮임", edit_parent.text())
        else:
            fail("S10", "editCloneParent", "없음")

        # notify path with what= argument
        RESULTS.append("\n## S11 on_settings_prefs_changed(what) 경로")
        save_last_commit_message("notify-path-msg")
        ctrl._on_settings_prefs_changed("message")
        if edit_msg is not None and edit_msg.text() == "notify-path-msg":
            ok("S11", "_on_settings_prefs_changed('message')")
        else:
            fail("S11", "notify message", repr(edit_msg.text() if edit_msg else None))

    finally:
        # restore
        save_last_private(snap["private"])
        save_last_commit_message(snap["msg"])
        save_last_publish_branch(snap["branch"])
        save_hide_real_email(snap["hide"])
        save_secret_pii_scan_enabled(snap["scan"])
        s = _settings()
        s.setValue("recent_folders", snap["recent"])
        window.close()

    RESULTS.append(f"\nTOTAL  PASS={PASS}  FAIL={FAIL}")
    print("\n".join(RESULTS))
    if FAIL:
        print("SETTINGS_TABS_SYNC_FAIL")
        return 1
    print("SETTINGS_TABS_SYNC_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
