"""Cross-check: PAT Note is stored/cleared at the same keyring level as the token.

Pipeline (both WebView + external browser):
  create URL (description=Note) → dialog.token_note() → PatLoginWorker
  → login_with_pat(pat_note=) → save_token(pat_note=) → load_pat_note()
  → delete_token() removes PAT_NOTE_USERNAME with the token.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.auth.pat_urls import classic_pat_create_url, note_from_pat_create_url
from app.auth.token_store import (
    PAT_NOTE_USERNAME,
    TOKEN_USERNAME,
    delete_token,
    load_pat_note,
    load_token,
    save_token,
)


def test_note_is_peer_of_token_in_keyring_constants() -> None:
    assert TOKEN_USERNAME.startswith("github_")
    assert PAT_NOTE_USERNAME.startswith("github_")
    assert "token" in TOKEN_USERNAME
    assert "note" in PAT_NOTE_USERNAME


def test_save_load_delete_pat_note_with_token() -> None:
    """Note persists beside the token and is wiped on delete_token()."""
    store: dict[str, str] = {}

    def _set(service: str, user: str, password: str) -> None:
        assert service == "CloneUp"
        store[user] = password

    def _get(service: str, user: str) -> str | None:
        return store.get(user)

    def _delete(service: str, user: str) -> None:
        store.pop(user, None)

    with (
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch(
            "app.auth.token_store.keyring.delete_password", side_effect=_delete
        ),
        patch(
            "app.auth.token_store.keyring.errors.PasswordDeleteError",
            Exception,
        ),
    ):
        save_token(
            "ghp_" + ("a" * 36),
            "repo",
            auth_kind="pat",
            expires_at="none",
            pat_note="CloneUp-20260826-120000",
        )
        assert load_token() is not None
        assert load_pat_note() == "CloneUp-20260826-120000"

        # Scope-only refresh must not wipe Note (pat_note omitted)
        save_token(
            "ghp_" + ("a" * 36),
            "repo,workflow",
            connected_at="2026-08-26T12:00:00Z",
        )
        assert load_pat_note() == "CloneUp-20260826-120000"

        # Empty note clears like empty expires
        save_token(
            "ghp_" + ("b" * 36),
            "repo",
            auth_kind="pat",
            pat_note="",
        )
        assert load_pat_note() is None

        save_token(
            "ghp_" + ("c" * 36),
            "repo",
            auth_kind="pat",
            pat_note="CloneUp-KEEP",
        )
        delete_token()
        assert load_token() is None
        assert load_pat_note() is None
        assert TOKEN_USERNAME not in store or store.get(TOKEN_USERNAME) is None
        assert PAT_NOTE_USERNAME not in store


def test_webview_and_external_expose_token_note_api() -> None:
    from app.ui.connect_webview import GitHubConnectWebPane
    from app.ui.external_pat_guide import ExternalBrowserPatGuide
    from app.ui.login_dialog import ConnectGitHubWizard

    assert hasattr(ConnectGitHubWizard, "token_note")
    assert hasattr(ExternalBrowserPatGuide, "token_note")
    assert callable(getattr(ConnectGitHubWizard, "token_note"))
    assert callable(getattr(ExternalBrowserPatGuide, "token_note"))
    # WebPane emits Note synchronously on load_url (reissue/auto-open/away)
    assert hasattr(GitHubConnectWebPane, "pat_create_note")


def test_create_url_note_extractable_for_load_url_sync() -> None:
    """load_url emits pat_create_note from this extraction (sync before setUrl)."""
    from app.auth.pat_urls import classic_pat_create_url, note_from_pat_create_url
    from app.ui.connect_webview import GitHubConnectWebPane

    note = "CloneUp-SYNC-NOTE-1"
    url = classic_pat_create_url(note=note)
    assert note_from_pat_create_url(url) == note
    assert hasattr(GitHubConnectWebPane, "pat_create_note")


def test_create_url_note_roundtrip_for_both_paths() -> None:
    note = "CloneUp-20260826-999999"
    url = classic_pat_create_url(note=note)
    assert note_from_pat_create_url(url) == note


def test_login_with_pat_persists_note() -> None:
    from app.auth.session import login_with_pat

    store: dict[str, str] = {}

    def _set(service: str, user: str, password: str) -> None:
        store[user] = password

    def _get(service: str, user: str) -> str | None:
        return store.get(user)

    fake_user = {
        "login": "tester",
        "_oauth_scopes": "repo",
    }
    with (
        patch("app.auth.session.get_authenticated_user", return_value=fake_user),
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch(
            "app.auth.token_store.keyring.delete_password",
            side_effect=lambda s, u: store.pop(u, None),
        ),
        patch(
            "app.auth.token_store.keyring.errors.PasswordDeleteError",
            Exception,
        ),
        patch("app.auth.session._lookup_expires_at_via_api", return_value=None),
    ):
        login_with_pat(
            "ghp_" + ("d" * 36),
            expires_at="none",
            pat_note="CloneUp-FROM-WIZARD",
        )
        assert store.get(PAT_NOTE_USERNAME) == "CloneUp-FROM-WIZARD"
        assert load_pat_note() == "CloneUp-FROM-WIZARD"


def test_device_flow_clears_stale_pat_note() -> None:
    """Device login must not leave a previous classic Note hanging."""
    from app.auth.session import login_device_flow

    store: dict[str, str] = {
        PAT_NOTE_USERNAME: "CloneUp-STALE",
        TOKEN_USERNAME: "old",
    }

    def _set(service: str, user: str, password: str) -> None:
        store[user] = password

    def _get(service: str, user: str) -> str | None:
        return store.get(user)

    def _delete(service: str, user: str) -> None:
        store.pop(user, None)

    fake_resp = MagicMock()
    fake_resp.access_token = "gho_" + ("e" * 36)
    fake_resp.scope = "repo"

    with (
        patch("app.auth.session.is_device_flow_allowed", return_value=True),
        patch("app.auth.session.get_github_client_id", return_value="cid"),
        patch("app.auth.session.get_github_scopes", return_value="repo"),
        patch("app.auth.session.run_device_flow", return_value=fake_resp),
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch("app.auth.token_store.keyring.delete_password", side_effect=_delete),
        patch(
            "app.auth.token_store.keyring.errors.PasswordDeleteError",
            Exception,
        ),
    ):
        login_device_flow(open_browser=False, copy_code=False)
        assert store.get(PAT_NOTE_USERNAME) is None
        assert load_pat_note() is None
