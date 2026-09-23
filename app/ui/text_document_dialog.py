"""Scrollable plain-text document dialog (이용약관 / 라이선스 / OSS 고지).

Sized with ``availableGeometry`` so the frame stays above the Windows taskbar
on short or scaled displays. QMessageBox with a long ``setText`` overflows.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.pill_scrollbar import wire_pill_scrollbars
from app.ui.theme import active_palette, sync_titlebar_theme


def _mono(base: QFont) -> QFont:
    f = QFont(base)
    f.setFamily("Consolas")
    if not f.exactMatch():
        f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(max(10.0, float(base.pointSizeF() or 11.0)))
    return f


def show_text_document_dialog(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    prefer_w: int = 640,
    prefer_h: int = 560,
) -> None:
    """Show *text* in a read-only scroll view, taskbar-safe."""
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setObjectName("textDocumentDialog")
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setStyleSheet(
        f"QDialog#textDocumentDialog {{ background: {p.bg_window}; color: {p.text}; }}"
        f"QPlainTextEdit#textDocumentView {{"
        f" background: {p.bg_input}; color: {p.text};"
        f" border: 1px solid {p.border_soft}; border-radius: 6px;"
        f" padding: 8px;"
        f"}}"
        f"QPushButton#textDocumentClose {{"
        f" background: {p.bg_muted}; color: {p.text_secondary};"
        f" border: 1px solid {p.border_input}; border-radius: 6px;"
        f" padding: 7px 16px; font-size: 12.5px;"
        f"}}"
        f"QPushButton#textDocumentClose:hover {{ background: {p.hover_muted}; }}"
    )

    root = QVBoxLayout(dlg)
    root.setContentsMargins(16, 14, 16, 14)
    root.setSpacing(12)

    view = QPlainTextEdit()
    view.setObjectName("textDocumentView")
    view.setReadOnly(True)
    view.setPlainText(text)
    view.setFont(_mono(view.font()))
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    wire_pill_scrollbars(view)
    root.addWidget(view, 1)

    foot = QHBoxLayout()
    foot.addStretch(1)
    close = QPushButton("닫기")
    close.setObjectName("textDocumentClose")
    close.setDefault(True)
    close.clicked.connect(dlg.accept)
    foot.addWidget(close, 0)
    root.addLayout(foot)

    def _fit() -> None:
        from app.util.screen_fit import (
            center_client_in_available,
            read_screen_info,
            screen_for_widget,
        )

        info = read_screen_info(screen_for_widget(dlg, anchor=parent))
        if info is None:
            dlg.setMinimumSize(min(480, prefer_w), 320)
            dlg.resize(prefer_w, prefer_h)
            return
        margin = 24
        max_w = max(400, info.available_w - margin)
        max_h = max(320, info.available_h - margin)
        # Soft mins shrink on short / scaled work areas so Ok/닫기 stays on-screen.
        min_w = min(560, max_w)
        min_h = min(360, max_h)
        dlg.setMinimumSize(min(480, min_w), min(280, min_h))
        cw = min(prefer_w, max_w)
        ch = min(prefer_h, max_h)
        cw = max(min(400, max_w), min(cw, max_w))
        ch = max(min(320, max_h), min(ch, max_h))
        x, y, cw, ch = center_client_in_available(
            info.available_x,
            info.available_y,
            info.available_w,
            info.available_h,
            cw,
            ch,
        )
        dlg.setGeometry(x, y, cw, ch)

    _fit()
    sync_titlebar_theme(dlg)
    QTimer.singleShot(0, _fit)
    dlg.exec()
