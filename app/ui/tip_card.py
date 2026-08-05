"""Collapsible tip card — G1 purpose line + G2 notes without permanent height."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class TipCard(QFrame):
    """
    Folded by default: one summary line + chevron.
    Expanded: summary + bullet body (tab-specific G2 hints).
    """

    def __init__(
        self,
        summary: str,
        body: str,
        parent: QWidget | None = None,
        *,
        object_name: str = "tipCard",
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._expanded = False

        self._btn = QPushButton(self)
        self._btn.setObjectName("tipCardHeader")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFlat(True)
        self._btn.clicked.connect(self.toggle)

        self._body = QLabel(body, self)
        self._body.setObjectName("tipCardBody")
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._body.hide()

        self._summary = summary.strip()
        self._sync_header()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        lay.addWidget(self._btn)
        lay.addWidget(self._body)

    def _sync_header(self) -> None:
        chevron = "▾" if self._expanded else "▸"
        action = "접기" if self._expanded else "도움말 보기"
        self._btn.setText(f"{chevron}  {self._summary}   ·  {action}")
        self._btn.setToolTip(
            "클릭하면 이 탭에서 자주 막히는 점을 펼치거나 접습니다."
        )

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._sync_header()
        # re-apply size hint so layout collapses cleanly
        self.updateGeometry()
        if self.parentWidget() is not None:
            self.parentWidget().updateGeometry()


def install_tip_card(
    placeholder: QWidget,
    *,
    summary: str,
    body: str,
    object_name: str = "tipCard",
) -> TipCard | None:
    """
    Replace a UI placeholder widget with a TipCard in the same layout slot.
    """
    parent = placeholder.parentWidget()
    if parent is None:
        return None
    layout = parent.layout()
    if layout is None:
        return None

    index = -1
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is not None and item.widget() is placeholder:
            index = i
            break
    if index < 0:
        return None

    card = TipCard(summary, body, parent, object_name=object_name)
    layout.removeWidget(placeholder)
    placeholder.hide()
    placeholder.setParent(None)
    placeholder.deleteLater()
    layout.insertWidget(index, card)
    return card
