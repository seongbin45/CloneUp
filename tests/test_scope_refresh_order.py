"""Cross-check: scope gate must run *after* live X-OAuth-Scopes refresh.

If keyring is stale-narrow, ensure_valid_token used to raise before GET /user,
so Settings never saw GitHub's real scopes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.auth.session import apply_oauth_scopes_from_user, ensure_valid_token
from app.auth.token_store import SCOPE_UNKNOWN, normalize_scope_string


def test_apply_oauth_scopes_comma_header_updates_keyring() -> None:
    user = {"_oauth_scopes": "repo, workflow", "login": "alice"}
    with (
        patch("app.auth.session.load_scope", return_value="public_repo"),
        patch("app.auth.session._save_scope_only") as save,
    ):
        out = apply_oauth_scopes_from_user("tok", user)
    assert out == "repo, workflow"
    save.assert_called_once()
    assert save.call_args[0][1] == "repo, workflow"


def test_apply_oauth_scopes_empty_header_unknown_when_empty_store() -> None:
    user = {"_oauth_scopes": "", "login": "alice"}
    with (
        patch("app.auth.session.load_scope", return_value=None),
        patch("app.auth.session._save_scope_only") as save,
    ):
        out = apply_oauth_scopes_from_user("tok", user)
    assert out == SCOPE_UNKNOWN
    save.assert_called_once()


def test_apply_oauth_scopes_empty_header_keeps_classic_list() -> None:
    user = {"_oauth_scopes": "", "login": "alice"}
    with (
        patch("app.auth.session.load_scope", return_value="repo"),
        patch("app.auth.session._save_scope_only") as save,
    ):
        out = apply_oauth_scopes_from_user("tok", user)
    assert out == "repo"
    save.assert_not_called()


def test_ensure_valid_token_refreshes_before_gate() -> None:
    """Stale keyring without repo must still call GET /user, then update+gate."""
    user = {"login": "bob", "_oauth_scopes": "gist, read:org, repo, workflow"}

    with (
        patch("app.auth.session.load_token", return_value="ghp_fake_token_xxxxx"),
        patch("app.auth.session.load_auth_kind", return_value="pat"),
        patch("app.auth.session.get_authenticated_user", return_value=user) as get_user,
        patch(
            "app.auth.session.apply_oauth_scopes_from_user",
            return_value="gist, read:org, repo, workflow",
        ) as apply,
        patch("app.auth.session.scopes_known", return_value=True),
        patch("app.auth.session.has_scope", side_effect=lambda s: s == "repo"),
        patch("app.auth.session.get_github_scopes", return_value="repo"),
    ):
        token, u = ensure_valid_token()

    get_user.assert_called_once()
    apply.assert_called_once()
    assert token == "ghp_fake_token_xxxxx"
    assert u["login"] == "bob"


def test_ensure_valid_token_gate_after_refresh_when_still_narrow() -> None:
    from app.auth.session import AuthError, MISSING_REPO_MARKER

    user = {"login": "bob", "_oauth_scopes": "public_repo"}

    with (
        patch("app.auth.session.load_token", return_value="ghp_fake_token_xxxxx"),
        patch("app.auth.session.load_auth_kind", return_value="pat"),
        patch("app.auth.session.get_authenticated_user", return_value=user),
        patch(
            "app.auth.session.apply_oauth_scopes_from_user",
            return_value="public_repo",
        ),
        patch("app.auth.session.scopes_known", return_value=True),
        patch("app.auth.session.has_scope", return_value=False),
        patch("app.auth.session.get_github_scopes", return_value="repo"),
        patch("app.auth.session.load_scope", return_value="public_repo"),
    ):
        with pytest.raises(AuthError) as ei:
            ensure_valid_token()
    assert MISSING_REPO_MARKER in str(ei.value)
    # Must have reached API (would have raised earlier only if pre-gate)
    assert "public_repo" in str(ei.value) or "repo" in str(ei.value)


def test_normalize_matches_github_docs_example() -> None:
    assert normalize_scope_string("gist, read:org, repo, workflow") == (
        "gist, read:org, repo, workflow"
    )
    # Space-only input still becomes comma display form
    assert normalize_scope_string("repo workflow") == "repo, workflow"


def test_refresh_scopes_401_clears_token() -> None:
    from app.auth.session import refresh_scopes_from_github
    from app.github.api_client import GitHubAPIError

    with (
        patch("app.auth.session.load_token", return_value="ghp_dead_token_xxxxx"),
        patch(
            "app.auth.session.get_authenticated_user",
            side_effect=GitHubAPIError(401, "bad credentials"),
        ),
        patch("app.auth.session.delete_token") as delete,
    ):
        scope, user = refresh_scopes_from_github()
    assert scope is None and user is None
    delete.assert_called_once()


def test_refresh_scopes_network_keeps_keyring() -> None:
    from app.auth.session import refresh_scopes_from_github

    with (
        patch("app.auth.session.load_token", return_value="ghp_ok_token_xxxxx"),
        patch(
            "app.auth.session.get_authenticated_user",
            side_effect=OSError("network down"),
        ),
        patch("app.auth.session.delete_token") as delete,
        patch("app.auth.session.load_scope", return_value="repo"),
    ):
        scope, user = refresh_scopes_from_github()
    assert scope == "repo"
    assert user is None
    delete.assert_not_called()


def test_main_settings_menu_refreshes_status_after_close() -> None:
    """Regression: settings may clear token (401) — status row must re-read keyring."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "ui"
        / "main_window.py"
    )
    text = src.read_text(encoding="utf-8")
    # Find on_settings_menu and require refresh after show_settings
    start = text.find("def on_settings_menu")
    assert start >= 0
    chunk = text[start : start + 900]
    assert "show_settings(" in chunk
    assert "_refresh_status_bar()" in chunk
    # refresh must appear after show_settings call site
    assert chunk.find("_refresh_status_bar()") > chunk.find("show_settings(")
