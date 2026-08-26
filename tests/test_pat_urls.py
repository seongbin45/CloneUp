"""Unique PAT Note / create URL helpers."""

from __future__ import annotations

import re

from app.auth.pat_urls import classic_pat_create_url, make_pat_note
from app.util.browser_address import looks_like_token_note_taken


def test_make_pat_note_format() -> None:
    n = make_pat_note()
    assert re.fullmatch(r"CloneUp-\d{8}-\d{6}", n), n


def test_classic_url_embeds_unique_note() -> None:
    u = classic_pat_create_url()
    assert "settings/tokens/new" in u
    assert "scopes=repo" in u
    assert "description=CloneUp-" in u


def test_html_note_taken_detection() -> None:
    html = (
        "<div>Validation failed: Note has already been taken</div>"
        "<input name='oauth_access[description]' value='CloneUp'/>"
    )
    assert looks_like_token_note_taken(
        "New personal access token",
        html,
        url="https://github.com/settings/tokens",
    )
