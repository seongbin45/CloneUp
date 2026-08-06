"""
Compact GitHub connect wizard (PAT only).

Short pages, minimal copy. Extra tips stay collapsed under 「자세히」.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import is_device_flow_allowed
from app.ui.theme import Palette, active_palette

PAT_CREATE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo&description=CloneUp"
)
PAT_LIST_URL = "https://github.com/settings/tokens"


def show_missing_repo_help(
    parent: QWidget | None,
    *,
    current_scopes: str = "",
    offer_reconnect: bool = True,
) -> bool:
    """
    Short, scannable dialog when PAT lacks ``repo``.

    Returns True if user chose to open the connect wizard again.
    """
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("저장소 권한")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setMaximumWidth(440)
    dlg.setStyleSheet(_dialog_style(p))

    title = QLabel("이 키로는 아직 연결할 수 없어요")
    title.setObjectName("wizTitle")
    title.setWordWrap(True)

    # One line cause — no essay
    why = QLabel("「repo」(저장소) 권한이 꺼져 있습니다.")
    why.setObjectName("wizLead")
    why.setWordWrap(True)

    steps = QLabel(
        "1. 아래에서 새 키 만들기\n"
        "2. repo 체크 ✓  ·  만료 90일 권장\n"
        "3. 생성 → 복사 → 다시 연결"
    )
    steps.setObjectName("wizBox")
    steps.setWordWrap(True)

    scopes = (current_scopes or "").strip()
    detail_bits = [
        "예전 키에는 권한을 나중에 붙일 수 없습니다. 새 키를 만드세요.",
    ]
    if scopes and scopes not in ("(없음)",):
        detail_bits.append(f"이 키에 있던 권한: {scopes}")
    detail = _DetailToggle("\n".join(detail_bits))

    btn_create = QPushButton("1. 새 키 만들기")
    btn_create.setObjectName("btnPrimary")
    btn_create.setDefault(True)
    btn_create.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(PAT_CREATE_URL))
    )

    reconnect = {"go": False}

    def _reconnect() -> None:
        reconnect["go"] = True
        dlg.accept()

    btn_again = QPushButton("3. 다시 연결")
    btn_again.setObjectName("btnPrimary")
    if offer_reconnect:
        btn_again.clicked.connect(_reconnect)
    else:
        btn_again.hide()

    btn_close = QPushButton("닫기")
    btn_close.setObjectName("btnGhost")
    btn_close.clicked.connect(dlg.reject)

    # Numbered actions match the 3 steps above
    actions = QHBoxLayout()
    actions.setSpacing(8)
    actions.addWidget(btn_create, 1)
    if offer_reconnect:
        actions.addWidget(btn_again, 1)

    bottom = QHBoxLayout()
    bottom.addWidget(btn_close)
    bottom.addStretch(1)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 12)
    lay.setSpacing(8)
    lay.addWidget(title)
    lay.addWidget(why)
    lay.addWidget(steps)
    lay.addLayout(actions)
    lay.addWidget(detail)
    lay.addLayout(bottom)

    dlg.exec()
    return bool(reconnect["go"])


def parse_scopes_from_missing_repo_message(message: str) -> str:
    """Extract trailing scope list from format_missing_repo_scope_error text."""
    for line in (message or "").splitlines():
        if line.startswith("이 키에 있던 권한:"):
            return line.split(":", 1)[-1].strip()
    return ""


def _dialog_style(p: Palette) -> str:
    return f"""
    QDialog {{
        background: {p.bg_window};
    }}
    QLabel#wizTitle {{
        color: {p.text};
        font-size: 16px;
        font-weight: 700;
    }}
    QLabel#wizLead {{
        color: {p.text_muted};
        font-size: 12.5px;
    }}
    QLabel#wizBox {{
        color: {p.text_secondary};
        font-size: 12.5px;
        background: {p.bg_muted};
        border: 1px solid {p.border_soft};
        border-radius: 8px;
        padding: 10px 12px;
    }}
    QLabel#wizProgress {{
        color: {p.primary};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#wizDetail {{
        color: {p.text_muted};
        font-size: 12px;
        padding: 4px 2px;
    }}
    QLineEdit#patEdit {{
        padding: 10px 12px;
        font-size: 13.5px;
        border: 1px solid {p.border_input};
        border-radius: 8px;
        background: {p.bg_input};
        color: {p.text};
    }}
    QPushButton#btnPrimary {{
        background: {p.primary};
        color: {p.text_on_primary};
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 13px;
        min-height: 32px;
    }}
    QPushButton#btnPrimary:hover {{
        background: {p.primary_hover};
    }}
    QPushButton#btnSecondary {{
        background: {p.bg_muted};
        color: {p.text};
        border: 1px solid {p.border_input};
        border-radius: 8px;
        padding: 8px 12px;
        font-weight: 600;
        font-size: 12.5px;
        min-height: 32px;
    }}
    QPushButton#btnSecondary:hover {{
        background: {p.hover_muted};
    }}
    QPushButton#btnGhost {{
        background: transparent;
        color: {p.text_muted};
        border: none;
        padding: 4px 6px;
        font-size: 12px;
    }}
    QPushButton#btnGhost:hover {{
        color: {p.primary};
    }}
    """


class _DetailToggle(QWidget):
    """Collapsed-by-default extra tips to keep the dialog short."""

    def __init__(self, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._open = False
        self._btn = QPushButton("자세히 ▾")
        self._btn.setObjectName("btnGhost")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._toggle)
        self._body = QLabel(body)
        self._body.setObjectName("wizDetail")
        self._body.setWordWrap(True)
        self._body.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._body)

    def _toggle(self) -> None:
        self._open = not self._open
        self._body.setVisible(self._open)
        self._btn.setText("접기 ▴" if self._open else "자세히 ▾")


class ConnectGitHubWizard(QDialog):
    """
    Compact 2-step connect: 키 만들기 → 붙여넣기.
    """

    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        super().__init__(parent)
        self._token = ""
        self._want_device = False
        self._reauth = reauth
        p = active_palette()

        self.setWindowTitle("GitHub 연결")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        # Prefer short height; content drives size
        self.setMinimumHeight(0)
        self.setStyleSheet(_dialog_style(p))

        self._progress = QLabel()
        self._progress.setObjectName("wizProgress")
        self._progress.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_make_key())
        self._stack.addWidget(self._page_paste())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        root.addWidget(self._progress)
        root.addWidget(self._stack)
        self._go(0)

    def token(self) -> str:
        return self._token

    def wants_device_flow(self) -> bool:
        return self._want_device

    def _go(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        labels = ("1 / 2  ·  키 만들기", "2 / 2  ·  붙여넣기")
        self._progress.setText(labels[index] if 0 <= index < 2 else "")
        self.adjustSize()
        if index == 1:
            self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _open_create_page(self) -> None:
        QDesktopServices.openUrl(QUrl(PAT_CREATE_URL))

    def _page_make_key(self) -> QWidget:
        w = QWidget()
        title = QLabel(
            "새 키로 다시 연결" if self._reauth else "GitHub 키 만들기"
        )
        title.setObjectName("wizTitle")

        lead = QLabel("브라우저에서 키를 만든 뒤, 다음 단계에 붙여 넣습니다.")
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)

        box = QLabel(
            "· repo 권한 켜기\n"
            "· 만료일: 90일 또는 없음 권장\n"
            "· 생성 후 초록 키 전체 복사"
        )
        box.setObjectName("wizBox")
        box.setWordWrap(True)

        detail = _DetailToggle(
            "키 = 비밀번호 대용 출입증. 채팅·캡처에 올리지 마세요.\n"
            "이 컴퓨터에만 저장됩니다. 만료되면 새 키가 필요합니다.\n"
            "영문 화면: Expiration → repo → Generate → Copy."
        )

        btn_open = QPushButton("브라우저에서 만들기")
        btn_open.setObjectName("btnPrimary")
        btn_open.setDefault(True)
        btn_open.clicked.connect(self._open_create_page)

        btn_list = QPushButton("키 목록")
        btn_list.setObjectName("btnSecondary")
        btn_list.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PAT_LIST_URL))
        )

        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)

        btn_next = QPushButton("복사했어요 →")
        btn_next.setObjectName("btnPrimary")
        btn_next.clicked.connect(lambda: self._go(1))

        top_btns = QHBoxLayout()
        top_btns.setSpacing(8)
        top_btns.addWidget(btn_open, 1)
        top_btns.addWidget(btn_list, 0)

        nav = QHBoxLayout()
        nav.addWidget(btn_cancel)
        nav.addStretch(1)
        nav.addWidget(btn_next)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(title)
        lay.addWidget(lead)
        lay.addWidget(box)
        lay.addLayout(top_btns)
        lay.addWidget(detail)
        if is_device_flow_allowed():
            btn_dev = QPushButton("개발용 장치 코드")
            btn_dev.setObjectName("btnGhost")
            btn_dev.clicked.connect(self._pick_device)
            lay.addWidget(btn_dev)
        lay.addLayout(nav)
        return w

    def _page_paste(self) -> QWidget:
        w = QWidget()
        title = QLabel("키 붙여 넣기")
        title.setObjectName("wizTitle")

        lead = QLabel("복사한 키를 붙여 넣고 연결을 누르세요. (Ctrl+V)")
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)

        self._edit = QLineEdit()
        self._edit.setObjectName("patEdit")
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("ghp_… 키 붙여 넣기")
        self._edit.setClearButtonEnabled(True)

        btn_paste = QPushButton("붙여넣기")
        btn_paste.setObjectName("btnSecondary")
        btn_paste.clicked.connect(self._paste_clipboard)

        self._btn_toggle = QPushButton("보기")
        self._btn_toggle.setObjectName("btnSecondary")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._on_toggle_visible)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(btn_paste)
        tools.addWidget(self._btn_toggle)
        tools.addStretch(1)

        detail = _DetailToggle(
            "키는 비밀번호와 같습니다. 남에게 보내지 마세요.\n"
            "잘못 붙여 넣으면 연결이 안 됩니다. 다시 복사하세요."
        )

        btn_back = QPushButton("← 이전")
        btn_back.setObjectName("btnGhost")
        btn_back.clicked.connect(lambda: self._go(0))

        btn_connect = QPushButton("연결")
        btn_connect.setObjectName("btnPrimary")
        btn_connect.setDefault(True)
        btn_connect.clicked.connect(self._finish)

        nav = QHBoxLayout()
        nav.addWidget(btn_back)
        nav.addStretch(1)
        nav.addWidget(btn_connect)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(title)
        lay.addWidget(lead)
        lay.addWidget(self._edit)
        lay.addLayout(tools)
        lay.addWidget(detail)
        lay.addLayout(nav)
        return w

    def _on_toggle_visible(self, checked: bool) -> None:
        if checked:
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_toggle.setText("숨김")
        else:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_toggle.setText("보기")

    def _paste_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if not text:
            QMessageBox.information(
                self, "클립보드 비어 있음", "브라우저에서 키를 먼저 복사하세요."
            )
            return
        self._edit.setText(text)
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _finish(self) -> None:
        raw = (self._edit.text() or "").strip()
        if not raw:
            QMessageBox.warning(self, "키 없음", "키를 붙여 넣은 뒤 연결을 누르세요.")
            return
        if len(raw) < 20:
            QMessageBox.warning(
                self, "너무 짧음", "키 전체를 복사했는지 확인하세요."
            )
            return
        self._token = raw
        self._want_device = False
        self.accept()

    def _pick_device(self) -> None:
        self._want_device = True
        self._token = ""
        self.accept()


# ----- Back-compat -----


class LoginMethodDialog(QDialog):
    METHOD_DEVICE = "device"
    METHOD_PAT = "pat"

    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        super().__init__(parent)
        self._method = self.METHOD_PAT
        self._wizard = ConnectGitHubWizard(parent, reauth=reauth)

    def exec(self) -> int:  # noqa: A003
        code = self._wizard.exec()
        if code == QDialog.DialogCode.Accepted:
            self._method = (
                self.METHOD_DEVICE
                if self._wizard.wants_device_flow()
                else self.METHOD_PAT
            )
            return int(QDialog.DialogCode.Accepted)
        return int(QDialog.DialogCode.Rejected)

    def selected_method(self) -> str:
        return self._method

    def wizard_token(self) -> str:
        return self._wizard.token()


class PatTokenDialog(ConnectGitHubWizard):
    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        super().__init__(parent, reauth=reauth)
