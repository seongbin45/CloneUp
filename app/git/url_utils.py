"""Normalize user-pasted GitHub URLs for git clone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_GITHUB_HOSTS = {"github.com", "www.github.com"}


class UrlError(Exception):
    pass


@dataclass(frozen=True)
class NormalizedCloneUrl:
    clone_url: str  # https://github.com/owner/repo.git
    owner: str
    repo: str
    warnings: tuple[str, ...] = ()


def normalize_github_clone_url(raw: str) -> NormalizedCloneUrl:
    """
    Accept common paste forms:

    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/main
    - https://github.com/owner/repo/blob/main/README.md
    - nina.v@example.com:owner/repo.git
    """
    s = (raw or "").strip()
    if not s:
        raise UrlError("저장소 주소를 입력하세요.")

    warnings: list[str] = []

    # SSH form
    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", s)
    if m:
        host, path = m.group(1), m.group(2).strip("/")
        if host not in _GITHUB_HOSTS and host != "github.com":
            # still allow other hosts later; for now GitHub-focused
            pass
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise UrlError("SSH 주소 형식이 올바르지 않습니다. 예: nina.v@example.com:owner/repo.git")
        owner, repo = parts[0], parts[1].removesuffix(".git")
        clone = f"https://github.com/{owner}/{repo}.git"
        if len(parts) > 2:
            warnings.append("경로 뒷부분(브랜치/파일)은 무시하고 저장소 루트만 받습니다.")
        return NormalizedCloneUrl(clone, owner, repo, tuple(warnings))

    # Add scheme if missing
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", s):
        s = "https://" + s

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower()
    if host not in _GITHUB_HOSTS:
        raise UrlError(
            "지금은 github.com 주소만 지원합니다. "
            "예: https://github.com/owner/repo"
        )

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise UrlError("주소에 owner/repo 가 없습니다. 예: https://github.com/owner/repo")

    owner, repo = parts[0], parts[1].removesuffix(".git")

    if len(parts) >= 3 and parts[2] in ("tree", "blob", "commits", "issues", "pull"):
        warnings.append(
            f"웹 주소(/{'/'.join(parts[2:])})는 무시합니다. 저장소 루트만 clone 합니다."
        )

    clone = f"https://github.com/{owner}/{repo}.git"
    return NormalizedCloneUrl(clone, owner, repo, tuple(warnings))
