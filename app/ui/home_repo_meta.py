"""Resolve GitHub ownership / visibility for home detail (P4b)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ui.home_tokens import display_path


@dataclass(frozen=True)
class HomeRepoMeta:
    is_mine: bool | None  # None = unknown → treat as mine for CTA
    origin_display: str
    visibility: str  # 공개 | 비공개 | —
    owner: str
    repo: str


def _parse_owner_repo(origin_url: str) -> tuple[str, str]:
    if not origin_url:
        return "", ""
    try:
        from app.git.url_utils import normalize_github_clone_url

        info = normalize_github_clone_url(origin_url)
        return (info.owner or "", (info.repo or "").removesuffix(".git"))
    except Exception:
        return "", ""


def resolve_home_repo_meta(
    folder: str | Path,
    *,
    login: str | None,
    network: bool = True,
) -> HomeRepoMeta:
    """Best-effort meta; never raises — falls back to safe defaults.

    ``network=False`` skips GitHub HTTP (UI thread). Callers should paint
    first with network=False, then refresh with network=True off-thread.
    """
    empty = HomeRepoMeta(
        is_mine=None,
        origin_display="—",
        visibility="—",
        owner="",
        repo="",
    )
    try:
        from app.git.sync_ops import get_repo_status

        st = get_repo_status(Path(folder))
    except Exception:
        return empty

    origin = (st.origin_url or "").strip()
    if not origin:
        return HomeRepoMeta(
            is_mine=True,  # no remote → "내 프로젝트" publish path
            origin_display="—",
            visibility="—",
            owner="",
            repo="",
        )

    owner, repo = _parse_owner_repo(origin)
    display = display_path(origin)
    if owner and repo:
        display = f"{owner}/{repo}"

    is_mine: bool | None = None
    visibility = "—"
    login_l = (login or "").strip().lower()
    if login_l and owner:
        is_mine = owner.lower() == login_l

    # Optional API enrichment — never on the first UI paint (timeout up to 30s)
    if network and owner and repo:
        try:
            from app.auth.token_store import load_token
            from app.github.api_client import get_repo_access

            tok = None
            try:
                tok = load_token()
            except Exception:
                tok = None
            access = get_repo_access(owner, repo, access_token=tok)
            if access:
                if "push" in access:
                    is_mine = bool(access.get("push"))
                if "private" in access:
                    visibility = "비공개" if access.get("private") else "공개"
        except Exception:
            pass

    return HomeRepoMeta(
        is_mine=is_mine,
        origin_display=display or "—",
        visibility=visibility,
        owner=owner,
        repo=repo,
    )
