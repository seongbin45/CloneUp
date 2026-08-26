"""Personal Access Token create URLs with unique Note names."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, quote, unquote, urlparse


def make_pat_note(*, prefix: str = "CloneUp") -> str:
    """``CloneUp-YYYYMMDD-HHMMSS`` — avoids 'Note has already been taken'."""
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def note_from_pat_create_url(url: str) -> str:
    """Extract Note/name from a classic or fine-grained create URL."""
    try:
        q = parse_qs(urlparse(url or "").query)
    except Exception:
        return ""
    for key in ("description", "name"):
        vals = q.get(key) or []
        if vals:
            return unquote(str(vals[0])).strip()
    return ""


def classic_pat_create_url(
    *,
    note: str | None = None,
    scopes: str = "repo",
) -> str:
    """GitHub classic token form with ``repo`` (or custom) scopes pre-checked."""
    n = (note or "").strip() or make_pat_note()
    return (
        "https://github.com/settings/tokens/new"
        f"?scopes={quote(scopes, safe=',')}&description={quote(n, safe='')}"
    )


def fine_pat_create_url(*, note: str | None = None) -> str:
    """Fine-grained token form (existing-repo sync; not for new-repo create)."""
    n = (note or "").strip() or make_pat_note()
    return (
        "https://github.com/settings/personal-access-tokens/new"
        f"?name={quote(n, safe='')}&contents=write"
    )


def workflow_pat_create_url(*, note: str | None = None) -> str:
    n = (note or "").strip() or make_pat_note()
    return classic_pat_create_url(note=n, scopes="repo,workflow")
