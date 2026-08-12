"""Cross-check: GitHub X-OAuth-Scopes is comma-separated; CloneUp must not
treat ``repo,`` as a different name than ``repo`` (권한 업데이트 false reject).
"""

from __future__ import annotations

import pytest

from app.auth.token_store import (
    normalize_scope_string,
    parse_oauth_scopes,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("repo", ["repo"]),
        ("repo user", ["repo", "user"]),
        # GitHub docs / live API examples
        ("repo, user", ["repo", "user"]),
        ("gist, read:org, repo, workflow", ["gist", "read:org", "repo", "workflow"]),
        ("repo,user", ["repo", "user"]),
        ("  repo,  workflow  ", ["repo", "workflow"]),
        ("", []),
        (None, []),
        # colon scopes must stay whole
        ("read:org, write:org", ["read:org", "write:org"]),
        ("repo:status, repo", ["repo:status", "repo"]),
    ],
)
def test_parse_oauth_scopes(raw: str | None, expected: list[str]) -> None:
    assert parse_oauth_scopes(raw) == expected


def test_normalize_dedupes_and_commas() -> None:
    """Canonical form is GitHub-style comma + space (설정·툴팁 표시용)."""
    assert normalize_scope_string("repo, user, repo") == "repo, user"
    assert normalize_scope_string("gist, read:org, repo, workflow") == (
        "gist, read:org, repo, workflow"
    )
    assert normalize_scope_string("repo user") == "repo, user"


def test_comma_form_must_detect_repo() -> None:
    """Regression: space-only split left 'repo,' so login rejected multi-scope PATs."""
    parts = set(parse_oauth_scopes("repo, user"))
    assert "repo" in parts
    assert "user" in parts
    assert "repo," not in parts


def test_old_buggy_split_would_fail() -> None:
    """Document the pre-fix failure mode against GitHub's documented header."""
    buggy = set("repo, user".split())
    assert "repo" not in buggy  # was False → false "missing repo"
    fixed = set(parse_oauth_scopes("repo, user"))
    assert "repo" in fixed
