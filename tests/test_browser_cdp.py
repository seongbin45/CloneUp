"""Unit tests for optional Path B CDP helpers (no live Chrome required)."""

from __future__ import annotations

import json

import pytest

from app.auth.pat_form_js import JS_CLICK_GENERATE_TOKEN, JS_SET_EXPIRATION
from app.util import browser_cdp as cdp


def test_cdp_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONEUP_CDP", raising=False)
    assert cdp.cdp_enabled() is False
    monkeypatch.setenv("CLONEUP_CDP", "1")
    assert cdp.cdp_enabled() is True
    monkeypatch.setenv("CLONEUP_CDP", "yes")
    assert cdp.cdp_enabled() is True


def test_probe_rejects_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cdp.probe_cdp_endpoint(host="8.8.8.8", port=9222) is None


def test_probe_parses_version_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"Browser": "Chrome/120", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/x"}

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _urlopen(req, timeout=0):  # noqa: ANN001
        return _Resp()

    monkeypatch.setattr(cdp.urllib.request, "urlopen", _urlopen)
    got = cdp.probe_cdp_endpoint(host="127.0.0.1", port=9222)
    assert got is not None
    assert "Browser" in got


def test_probe_returns_none_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(cdp.urllib.request, "urlopen", _boom)
    assert cdp.probe_cdp_endpoint() is None


def test_shared_pat_js_mentions_hidden_field() -> None:
    assert "default_expires_at" in JS_SET_EXPIRATION
    assert "Generate token" in JS_CLICK_GENERATE_TOKEN


def test_page_pat_score_prefers_tokens_new() -> None:
    weak = cdp._page_pat_score("https://www.google.com/search?q=x", "Google")
    strong = cdp._page_pat_score(
        "https://github.com/settings/tokens/new",
        "New Personal Access Token (Classic)",
    )
    assert strong > weak
    assert strong >= 40
    # Login/home alone must not reach the picker threshold (≥40).
    login = cdp._page_pat_score("https://github.com/login", "Sign in to GitHub")
    assert login < 40


def test_pick_pat_page_ignores_weak_github_tabs() -> None:
    class _Page:
        def __init__(self, url: str, title: str) -> None:
            self.url = url
            self._title = title

        def title(self) -> str:
            return self._title

    class _Browser:
        def __init__(self, pages: list) -> None:
            self.contexts = [type("C", (), {"pages": pages})()]

    browser = _Browser(
        [
            _Page("https://github.com/", "GitHub"),
            _Page("https://github.com/login", "Sign in to GitHub"),
        ]
    )
    assert cdp._pick_pat_page(browser) is None

    browser2 = _Browser(
        [
            _Page("https://github.com/login", "Sign in"),
            _Page(
                "https://github.com/settings/tokens/new",
                "New Personal Access Token (Classic)",
            ),
        ]
    )
    picked = cdp._pick_pat_page(browser2)
    assert picked is not None
    assert "tokens/new" in picked.url


def test_cdp_profile_dir_under_cloneup(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = cdp.cdp_profile_dir()
    assert path.name == "cdp-profile"
    assert path.parent.name == "CloneUp"
    assert path.is_dir()


def test_cdp_endpoint_url_rejects_non_loopback() -> None:
    with pytest.raises(ValueError):
        cdp.cdp_endpoint_url(host="192.168.1.1", port=9222)


def test_with_cdp_browser_never_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLONEUP_CDP", "1")
    monkeypatch.setattr(
        cdp,
        "probe_cdp_endpoint",
        lambda **_k: {"Browser": "Chrome/1"},
    )

    closed: list[bool] = []

    class _Browser:
        def close(self) -> None:
            closed.append(True)

        @property
        def contexts(self):
            return []

    class _Chromium:
        def connect_over_cdp(self, _url: str):
            return _Browser()

    class _P:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _PW:
        def sync_playwright(self):
            return _P()

    import sys
    import types

    fake = types.ModuleType("playwright")
    fake_sync = types.ModuleType("playwright.sync_api")
    fake_sync.sync_playwright = lambda: _P()
    sys.modules["playwright"] = fake
    sys.modules["playwright.sync_api"] = fake_sync

    def _run(browser):
        return True, "ok"

    try:
        ok, detail = cdp._with_cdp_browser(_run)
        assert ok is True
        assert detail == "ok"
        assert closed == [], "CDP path must not call browser.close()"
    finally:
        sys.modules.pop("playwright.sync_api", None)
        sys.modules.pop("playwright", None)


def test_set_expiration_disabled_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONEUP_CDP", raising=False)
    ok, detail = cdp.set_pat_expiration_cdp("90")
    assert ok is False
    assert detail == "cdp-disabled"


def test_fallback_helper_uses_uia_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONEUP_CDP", raising=False)
    calls: list[str] = []

    def _uia(days: str) -> tuple[bool, str]:
        calls.append(days)
        return True, "uia-ok"

    ok, detail = cdp.try_cdp_expiration_then_uia_fallback("90", uia_fallback=_uia)
    assert ok is True
    assert detail == "uia-ok"
    assert calls == ["90"]


def test_generate_fallback_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONEUP_CDP", raising=False)
    ok, detail = cdp.try_cdp_generate_then_uia_fallback(
        uia_fallback=lambda: (True, "uia-gen")
    )
    assert ok is True
    assert detail == "uia-gen"


def test_wait_for_cdp_ready_succeeds_on_later_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits = {"n": 0}

    def _probe(**_k):
        hits["n"] += 1
        return {"Browser": "Chrome"} if hits["n"] >= 3 else None

    monkeypatch.setattr(cdp, "probe_cdp_endpoint", _probe)
    import time as time_mod

    monkeypatch.setattr(time_mod, "sleep", lambda _s: None)
    assert cdp.wait_for_cdp_ready(attempts=5, interval_s=0.01) is True
    assert hits["n"] >= 3
