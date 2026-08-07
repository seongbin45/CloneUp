"""Smoke tests for list_user_repos helper shape (no network)."""

from __future__ import annotations

from app.auth.token_store import is_logged_in, load_token
from app.github.api_client import list_user_repos


def test_list_user_repos_empty_token() -> None:
    assert list_user_repos("") == []
    assert list_user_repos("   ") == []


def test_is_logged_in_matches_token() -> None:
    """Helper stays in sync with load_token (boolean)."""
    assert is_logged_in() is bool(load_token())
