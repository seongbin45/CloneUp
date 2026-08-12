"""Smoke tests for list_user_repos helper shape (no network)."""

from __future__ import annotations

from app.auth.token_store import is_logged_in
from app.github.api_client import list_user_repos


def test_list_user_repos_empty_token() -> None:
    assert list_user_repos("") == []
    assert list_user_repos("   ") == []


def test_is_logged_in_matches_token() -> None:
    """Helper stays in sync with load_token (boolean). Uses mocks — real
    keyring can hang on headless Windows CI."""
    from unittest.mock import patch

    with patch("app.auth.token_store.load_token", return_value="ghp_x"):
        assert is_logged_in() is True
    with patch("app.auth.token_store.load_token", return_value=None):
        assert is_logged_in() is False
    with patch("app.auth.token_store.load_token", return_value=""):
        assert is_logged_in() is False
