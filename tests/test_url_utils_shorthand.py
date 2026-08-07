"""URL normalize accepts list labels and owner/repo shorthand."""

from __future__ import annotations

import pytest

from app.git.url_utils import UrlError, normalize_github_clone_url


def test_owner_repo_shorthand() -> None:
    n = normalize_github_clone_url("seongbin45/CloneUp")
    assert n.owner == "seongbin45"
    assert n.repo == "CloneUp"
    assert n.display_url == "https://github.com/seongbin45/CloneUp"
    assert n.clone_url.endswith(".git")


def test_list_label_private_suffix() -> None:
    n = normalize_github_clone_url("seongbin45/CloneUp  ·  비공개")
    assert n.display_url == "https://github.com/seongbin45/CloneUp"


def test_list_label_middle_dot() -> None:
    n = normalize_github_clone_url("o/r · private")
    assert n.display_url == "https://github.com/o/r"


def test_full_https_still_works() -> None:
    n = normalize_github_clone_url("https://github.com/a/b/tree/main")
    assert n.display_url == "https://github.com/a/b"
    assert n.suggested_branch == "main"


def test_rejects_garbage() -> None:
    with pytest.raises(UrlError):
        normalize_github_clone_url("not a repo")
