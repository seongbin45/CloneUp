"""Normalize user-pasted GitHub URLs for git clone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

_GITHUB_HOSTS = {"github.com", "www.github.com"}
# Path segments after owner/repo that mean "not a branch name" for display cleanup
_WEB_SECTIONS = frozenset(
    {
        "tree",
        "blob",
        "commits",
        "commit",
        "issues",
        "pull",
        "pulls",
        "actions",
        "projects",
        "wiki",
        "security",
        "settings",
        "pulse",
        "graphs",
        "network",
        "community",
        "discussions",
        "releases",
        "tags",
        "branches",
        "archive",
        "raw",
        "blame",
        "find",
        "search",
        "compare",
        "forks",
        "stargazers",
        "watchers",
    }
)


class UrlError(Exception):
    pass


def is_github_https_host(host: str | None) -> bool:
    h = (host or "").lower().strip()
    return h in _GITHUB_HOSTS


def assert_github_https_remote(url: str, *, what: str = "origin") -> str:
    """
    Ensure a remote URL is clean https://github.com/... (P2 / M3 review).

    Rejects SSH, non-github hosts, and credential-embedded URLs.
    Returns the stripped URL for convenience.
    """
    s = (url or "").strip()
    if not s:
        raise UrlError(f"{what} 주소가 비어 있습니다.")
    low = s.lower()
    if "x-access-token" in low:
        raise UrlError(
            f"{what} 주소에 비밀 정보가 들어 있습니다. 안전을 위해 막았습니다."
        )
    if re.match(r"^git@([^:]+):", s, re.I):
        raise UrlError(
            f"{what} 이 SSH 주소입니다. CloneUp은 https://github.com/… 만 지원합니다."
        )
    raw = s if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", s) else "https://" + s
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not is_github_https_host(host):
        raise UrlError(
            f"{what} 이 github.com 이 아닙니다 ({host or '?'}).\n"
            "CloneUp은 github.com HTTPS 원격만 지원합니다."
        )
    if parsed.username or parsed.password:
        raise UrlError(
            f"{what} 주소에 사용자/비밀번호가 들어 있습니다. 깨끗한 HTTPS 주소만 쓰세요."
        )
    return s

@dataclass(frozen=True)
class NormalizedCloneUrl:
    clone_url: str  # https://github.com/owner/repo.git
    display_url: str  # https://github.com/owner/repo (for the paste field)
    owner: str
    repo: str
    suggested_branch: str | None = None  # from /tree/… or /blob/… if present
    warnings: tuple[str, ...] = ()


def _branch_from_web_path(parts: list[str]) -> str | None:
    """
    From [owner, repo, tree|blob, …] take a simple branch hint.

    Multi-segment branch names (feature/foo) are not fully recovered when a
    file path follows; the branch combo still lets the user pick the real name.
    """
    if len(parts) < 4:
        return None
    if parts[2] not in ("tree", "blob", "commits", "raw", "blame"):
        return None
    branch = unquote(parts[3]).strip()
    if not branch or branch in (".", ".."):
        return None
    return branch


def normalize_github_clone_url(raw: str) -> NormalizedCloneUrl:
    """
    Accept common paste forms and always reduce to owner/repo root.

    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/main/...
    - https://github.com/owner/repo/blob/main/README.md
    - nina.v@example.com:owner/repo.git

    Any path after owner/repo is stripped. Branch is only a *suggestion*
    when the URL used /tree/ or /blob/.
    """
    s = (raw or "").strip()
    if not s:
        raise UrlError("저장소 주소를 입력하세요.")

    # UI list labels: "owner/repo  ·  비공개" → owner/repo
    if "  ·  " in s:
        s = s.split("  ·  ", 1)[0].strip()
    elif " · " in s:
        s = s.split(" · ", 1)[0].strip()

    warnings: list[str] = []
    suggested: str | None = None

    # Shorthand owner/repo (from list selection / autocomplete)
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s):
        owner, repo = s.split("/", 1)
        display = f"https://github.com/{owner}/{repo}"
        return NormalizedCloneUrl(
            f"{display}.git",
            display,
            owner,
            repo.removesuffix(".git"),
            None,
            (),
        )

    # SSH form: nina.v@example.com:owner/repo.git
    m = re.match(r"^git@([^:]+):(.+)$", s)
    if m:
        host, path = m.group(1).lower(), m.group(2).strip().strip("/")
        if host not in _GITHUB_HOSTS:
            raise UrlError(
                "지금은 github.com 주소만 지원합니다.\n"
                "예: https://github.com/사용자/저장소"
            )
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise UrlError(
                "주소 형식이 올바르지 않습니다.\n"
                "예: nina.v@example.com:사용자/저장소.git"
            )
        owner, repo = parts[0], parts[1].removesuffix(".git")
        if len(parts) > 2:
            warnings.append(
                "주소 뒤 경로는 지우고 저장소 루트만 사용합니다. "
                "branch는 아래에서 고르세요."
            )
            suggested = _branch_from_web_path(
                [owner, repo, "tree"] + parts[2:]
            ) or (parts[2] if parts[2] not in _WEB_SECTIONS else None)
        display = f"https://github.com/{owner}/{repo}"
        return NormalizedCloneUrl(
            f"{display}.git",
            display,
            owner,
            repo,
            suggested,
            tuple(warnings),
        )

    # Add scheme if missing
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", s):
        s = "https://" + s

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower()
    if host not in _GITHUB_HOSTS:
        raise UrlError(
            "지금은 github.com 주소만 지원합니다.\n"
            "예: https://github.com/사용자/저장소"
        )

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise UrlError(
            "주소에 사용자/저장소 이름이 없습니다.\n"
            "예: https://github.com/사용자/저장소"
        )

    owner, repo = parts[0], parts[1].removesuffix(".git")
    extra = parts[2:]
    if extra:
        suggested = _branch_from_web_path(parts)
        warnings.append(
            "주소 뒤 경로는 지우고 저장소 루트만 남깁니다. "
            "branch는 아래에서 고르세요."
        )

    display = f"https://github.com/{owner}/{repo}"
    return NormalizedCloneUrl(
        f"{display}.git",
        display,
        owner,
        repo,
        suggested,
        tuple(warnings),
    )
