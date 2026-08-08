"""Unit tests for remote GitHub commit history helpers (no live network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.github.api_client import (
    GitHubAPIError,
    _parse_gh_iso_unix,
    compare_remote_commits,
    list_remote_changed_files,
    list_repo_commits,
)


def test_parse_gh_iso_unix_z() -> None:
    # 2024-01-15T12:00:00Z
    u = _parse_gh_iso_unix("2024-01-15T12:00:00Z")
    assert u > 1_700_000_000
    assert _parse_gh_iso_unix("") == 0
    assert _parse_gh_iso_unix("not-a-date") == 0


def test_list_repo_commits_maps_payload() -> None:
    payload = [
        {
            "sha": "abcdef0123456789abcdef0123456789abcdef01",
            "commit": {
                "author": {
                    "name": "Alice",
                    "date": "2024-08-07T05:02:00Z",
                },
                "message": "첫 줄 메시지\n\n본문 더 있음",
            },
            "author": {"login": "alice"},
        }
    ]
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = payload

    with patch("app.github.api_client.requests.get", return_value=mock_resp) as get:
        rows = list_repo_commits("octocat", "Hello-World", per_page=4, page=1)

    get.assert_called_once()
    kwargs = get.call_args.kwargs
    assert kwargs["params"]["page"] == 1
    assert kwargs["params"]["per_page"] == 4
    # No token → no Authorization header
    assert "Authorization" not in kwargs["headers"]

    assert len(rows) == 1
    c = rows[0]
    assert c.full_hash.startswith("abcdef")
    assert c.short_hash == "abcdef0"
    assert c.author == "Alice"
    assert c.message == "첫 줄 메시지"
    assert c.file_count == 0
    assert c.unix_time > 0


def test_list_repo_commits_uses_token_when_given() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = []

    with patch("app.github.api_client.requests.get", return_value=mock_resp) as get:
        list_repo_commits("o", "r", access_token="gho_test_token")

    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer gho_test_token"


def test_list_repo_commits_404_friendly() -> None:
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_resp.json.return_value = {"message": "Not Found"}

    with patch("app.github.api_client.requests.get", return_value=mock_resp):
        with pytest.raises(GitHubAPIError) as ei:
            list_repo_commits("nope", "missing")
    assert "찾을 수 없습니다" in str(ei.value)
    assert "nope/missing" in str(ei.value)


def test_list_remote_changed_files_status_map() -> None:
    payload = {
        "sha": "abc",
        "files": [
            {"filename": "a.py", "status": "added"},
            {"filename": "b.py", "status": "modified"},
            {"filename": "c.py", "status": "removed"},
            {"filename": "d.py", "status": "renamed"},
        ],
    }
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = payload

    with patch("app.github.api_client.requests.get", return_value=mock_resp):
        files = list_remote_changed_files("o", "r", "abc")

    kinds = [(f.kind, f.path) for f in files]
    assert kinds == [
        ("A", "a.py"),
        ("M", "b.py"),
        ("D", "c.py"),
        ("R", "d.py"),
    ]


def test_compare_remote_commits_status_map_and_url() -> None:
    payload = {
        "files": [
            {"filename": "new.py", "status": "added"},
            {"filename": "kept.py", "status": "modified"},
            {"filename": "gone.py", "status": "removed"},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = payload

    with patch(
        "app.github.api_client.requests.get", return_value=mock_resp
    ) as get:
        files = compare_remote_commits("o", "r", "head-sha", "target-sha")

    url = get.call_args.args[0]
    assert url.endswith("/repos/o/r/compare/head-sha...target-sha")
    kinds = [(f.kind, f.path) for f in files]
    assert kinds == [
        ("A", "new.py"),
        ("M", "kept.py"),
        ("D", "gone.py"),
    ]


def test_compare_remote_commits_requires_all_args() -> None:
    with pytest.raises(GitHubAPIError):
        compare_remote_commits("o", "r", "", "target-sha")
