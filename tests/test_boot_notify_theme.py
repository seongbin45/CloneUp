"""Boot toast follows 시안 light card (desin/CloneUp 시작 알림.dc.html)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QFrame

from app.ui.boot_notify import BootNotifyToast, _toast_qss
from app.ui.boot_scan import ChangedFile, PendingFolder


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_toast_qss_matches_design_tokens(qapp) -> None:
    qss = _toast_qss()
    # 시안 card
    assert "border-radius: 10px" in qss
    assert "#fbfaf8" in qss
    assert "#f2efe9" in qss
    assert "#b9bdc4" in qss
    assert "#1f6f5c" in qss
    # Transparent shell + inner card (bottom corners clip)
    assert "bootToastShell" in qss
    assert "bootToastCard" in qss
    assert "background: transparent" in qss


def test_toast_widget_has_rounded_card_shell(qapp) -> None:
    pf = PendingFolder(
        path="C:/tmp/demo",
        name="demo",
        files=(ChangedFile("M", "a.py", "#8a6d12"),),
        dirty=True,
        ahead=0,
        file_count=1,
    )
    toast = BootNotifyToast([pf])
    try:
        assert toast.objectName() == "bootToastShell"
        card = toast.findChild(QFrame, "bootToastCard")
        assert card is not None
        assert toast.width() == 382
        ss = toast.styleSheet()
        assert "border-radius: 10px" in ss
        assert card.graphicsEffect() is not None
    finally:
        toast.close()
