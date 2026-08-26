"""Path B assist worker — runs CDP/UIA off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.path_b_assist_worker import PathBAssistWorker


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
