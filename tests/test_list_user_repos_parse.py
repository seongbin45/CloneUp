"""Smoke tests for list_user_repos helper shape (no network)."""

from __future__ import annotations

from app.github.api_client import list_user_repos


def test_list_user_repos_empty_token() -> None:
    assert list_user_repos("") == []
    assert list_user_repos("   ") == []
