"""Path B assist worker — runs CDP/UIA off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.path_b_assist_worker import PathBAddressWorker, PathBAssistWorker
from app.util.browser_address import _is_connect_flow_url


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_assist_worker_expiry_falls_back_when_cdp_off(monkeypatch) -> None:
    _app()
    monkeypatch.delenv("CLONEUP_CDP", raising=False)

    def _uia(days: str, allow_click: bool = True):
        return True, f"uia:{days}"

    monkeypatch.setattr(
        "app.util.browser_address.try_set_token_expiration_uia",
        _uia,
    )

    results: list[tuple[str, bool, str]] = []

    worker = PathBAssistWorker("expiry", days="90")
    # DirectConnection: slot runs in worker thread so wait() sees the result.
    worker.finished_result.connect(
        lambda op, ok, detail: results.append((op, ok, detail)),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(5000)
    assert results
    op, ok, detail = results[-1]
    assert op == "expiry"
    assert ok is True
    assert "uia:90" in detail or detail.startswith("uia:")


def test_assist_worker_unknown_op() -> None:
    _app()
    results: list[tuple[str, bool, str]] = []
    worker = PathBAssistWorker("nope")
    worker.finished_result.connect(
        lambda op, ok, detail: results.append((op, ok, detail)),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(3000)
    assert results[-1][0] == "nope"
    assert results[-1][1] is False


def test_connect_flow_url_helper() -> None:
    assert _is_connect_flow_url("https://github.com/login")
    assert _is_connect_flow_url("https://accounts.google.com/v3/signin")
    assert not _is_connect_flow_url("https://intel.co.kr/support")
    assert not _is_connect_flow_url("https://youtube.com/watch?v=1")


def test_guide_has_open_token_create_page() -> None:
    """Regression: chip rewrite once dropped this and stuck LOGIN_WAIT."""
    from app.ui.external_pat_guide import ExternalBrowserPatGuide

    assert callable(getattr(ExternalBrowserPatGuide, "_open_token_create_page", None))


def test_address_worker_emits_sample(monkeypatch) -> None:
    _app()

    class _Fake:
        url = "https://github.com/"
        window_title = "GitHub"
        ui_text = "Dashboard"

    monkeypatch.setattr(
        "app.util.browser_address.read_browser_page_sample",
        lambda: _Fake(),
    )
    got: list[object] = []
    worker = PathBAddressWorker()
    worker.sample_ready.connect(
        lambda s: got.append(s),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(3000)
    assert got and getattr(got[-1], "url", "") == "https://github.com/"
