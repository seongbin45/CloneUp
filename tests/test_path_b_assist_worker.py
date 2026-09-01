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
    worker = PathBAddressWorker(read_expiry=False)
    worker.sample_ready.connect(
        lambda s: got.append(s),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(3000)
    assert got and isinstance(got[-1], dict)
    assert getattr(got[-1]["sample"], "url", "") == "https://github.com/"
    assert got[-1]["expiry_days"] is None


def test_address_worker_reads_expiry(monkeypatch) -> None:
    _app()

    class _Fake:
        url = "https://github.com/settings/tokens/new"
        window_title = "New personal access token"
        ui_text = "Expiration"

    monkeypatch.setattr(
        "app.util.browser_address.read_browser_page_sample",
        lambda: _Fake(),
    )
    monkeypatch.setattr(
        "app.util.expiry_ocr.read_token_expiration_ocr",
        lambda: ("30", "ocr:near-label:30-days"),
    )
    got: list[object] = []
    worker = PathBAddressWorker(read_expiry=True, sample_address=False)
    worker.sample_ready.connect(
        lambda s: got.append(s),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(3000)
    assert got[-1]["expiry_days"] == "30"
    assert "ocr:" in got[-1]["expiry_detail"]
    assert got[-1]["sample"] is None


def test_address_worker_expiry_falls_back_to_uia(monkeypatch) -> None:
    _app()

    class _Fake:
        url = "https://github.com/settings/tokens/new"
        window_title = "New personal access token"
        ui_text = "Expiration"

    monkeypatch.setattr(
        "app.util.browser_address.read_browser_page_sample",
        lambda: _Fake(),
    )
    monkeypatch.setattr(
        "app.util.expiry_ocr.read_token_expiration_ocr",
        lambda: (None, "ocr-no-match"),
    )
    monkeypatch.setattr(
        "app.util.browser_address.read_token_expiration_uia",
        lambda: ("90", "opener:90 days"),
    )
    got: list[object] = []
    worker = PathBAddressWorker(read_expiry=True, sample_address=False)
    worker.sample_ready.connect(
        lambda s: got.append(s),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(3000)
    assert got[-1]["expiry_days"] == "90"
    assert "uia:" in got[-1]["expiry_detail"]
