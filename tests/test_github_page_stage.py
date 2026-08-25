"""GitHub page stage detection from URL / title / HTML markers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.auth.github_page_stage import (
    GitHubPageStage,
    PageSnapshot,
    detect_github_page_stage,
    stage_label_ko,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "github_pages"
TEMP = Path(__file__).resolve().parents[1] / "temp"


def _html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("login_sign_in.html", GitHubPageStage.LOGIN),
        ("token_classic_new.html", GitHubPageStage.TOKEN_CLASSIC_NEW),
        ("token_classic_list.html", GitHubPageStage.TOKEN_CLASSIC_LIST),
        ("token_issued.html", GitHubPageStage.TOKEN_ISSUED),
        ("auth_2fa.html", GitHubPageStage.AUTH_2FA),
    ],
)
def test_fixtures_html(name: str, expected: GitHubPageStage) -> None:
    assert detect_github_page_stage(PageSnapshot(html=_html(name))) == expected


def test_url_paths() -> None:
    assert (
        detect_github_page_stage(
            PageSnapshot(
                url="https://github.com/login?return_to=https%3A%2F%2Fgithub.com%2Fsettings%2Ftokens%2Fnew%3Fscopes%3Drepo"
            )
        )
        == GitHubPageStage.LOGIN
    )
    assert (
        detect_github_page_stage(
            PageSnapshot(url="https://github.com/settings/tokens/new?scopes=repo&description=CloneUp")
        )
        == GitHubPageStage.TOKEN_CLASSIC_NEW
    )
    assert (
        detect_github_page_stage(
            PageSnapshot(url="https://github.com/settings/personal-access-tokens/new")
        )
        == GitHubPageStage.TOKEN_FINE_NEW
    )
    assert (
        detect_github_page_stage(PageSnapshot(url="https://github.com/settings/tokens"))
        == GitHubPageStage.TOKEN_CLASSIC_LIST
    )
    assert (
        detect_github_page_stage(
            PageSnapshot(url="https://github.com/settings/tokens?type=beta")
        )
        == GitHubPageStage.TOKEN_CLASSIC_LIST
    )
    assert (
        detect_github_page_stage(
            PageSnapshot(url="https://github.com/settings/personal-access-tokens")
        )
        == GitHubPageStage.TOKEN_FINE_LIST
    )
    assert (
        detect_github_page_stage(
            PageSnapshot(url="https://github.com/sessions/two-factor")
        )
        == GitHubPageStage.AUTH_2FA
    )


def test_empty_unknown() -> None:
    assert detect_github_page_stage(PageSnapshot()) == GitHubPageStage.UNKNOWN
    assert (
        detect_github_page_stage(PageSnapshot(url="https://github.com/seongbin45/CloneUp"))
        == GitHubPageStage.UNKNOWN
    )


def test_list_vs_issued() -> None:
    """Zip dump is the classic token *list*; issued needs copy-now + secret."""
    assert (
        detect_github_page_stage(PageSnapshot(html=_html("token_classic_list.html")))
        == GitHubPageStage.TOKEN_CLASSIC_LIST
    )
    assert (
        detect_github_page_stage(PageSnapshot(html=_html("token_issued.html")))
        == GitHubPageStage.TOKEN_ISSUED
    )


def test_stage_label_ko() -> None:
    assert "로그인" in stage_label_ko(GitHubPageStage.LOGIN)
    assert "복사" in stage_label_ko(GitHubPageStage.TOKEN_ISSUED)


@pytest.mark.skipif(
    not (TEMP / "Github_로그인_화면.html").is_file(),
    reason="local temp login dump not present",
)
def test_optional_temp_login_dump() -> None:
    html = (TEMP / "Github_로그인_화면.html").read_text(encoding="utf-8", errors="replace")
    assert detect_github_page_stage(PageSnapshot(html=html)) == GitHubPageStage.LOGIN


@pytest.mark.skipif(
    not (TEMP / "Github_Classic_Key_만들기.html").is_file(),
    reason="local temp classic-new dump not present",
)
def test_optional_temp_classic_new_dump() -> None:
    html = (TEMP / "Github_Classic_Key_만들기.html").read_text(
        encoding="utf-8", errors="replace"
    )
    assert (
        detect_github_page_stage(PageSnapshot(html=html))
        == GitHubPageStage.TOKEN_CLASSIC_NEW
    )
