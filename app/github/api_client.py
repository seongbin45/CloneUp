"""Minimal GitHub REST helpers (spike)."""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.git.history import ChangedFile, CommitInfo, format_abs_time

API_BASE = "https://api.github.com"
DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "CloneUp-spike/0.1",
}


class GitHubAPIError(Exception):
    def __init__(self, status: int, message: str, *, body: dict[str, Any] | None = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.body = body or {}


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {access_token}",
    }


def _raise_for_status(resp: requests.Response) -> None:
    if resp.ok:
        return
    body: dict[str, Any] = {}
    text = resp.text[:500]
    try:
        parsed = resp.json()
        if isinstance(parsed, dict):
            body = parsed
            text = parsed.get("message", text)
            errors = parsed.get("errors")
            if errors:
                text = f"{text} | errors={errors}"
    except ValueError:
        pass
    raise GitHubAPIError(resp.status_code, text, body=body)


def get_authenticated_user(access_token: str) -> dict[str, Any]:
    """
    GET /user.

    Also attaches `_oauth_scopes` from the X-OAuth-Scopes response header when
    present, so callers can persist granted scopes without re-login.
    """
    resp = requests.get(
        f"{API_BASE}/user",
        headers=_auth_headers(access_token),
        timeout=30,
    )
    _raise_for_status(resp)
    data = resp.json()
    scopes = resp.headers.get("X-OAuth-Scopes") or resp.headers.get("x-oauth-scopes")
    if scopes is not None:
        data["_oauth_scopes"] = scopes
    return data


def _repo_headers(access_token: str | None = None) -> dict[str, str]:
    headers = {**DEFAULT_HEADERS}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def get_repo_default_branch(
    owner: str,
    repo: str,
    *,
    access_token: str | None = None,
) -> str | None:
    """GET /repos/{owner}/{repo} → default_branch (e.g. main)."""
    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{repo}",
        headers=_repo_headers(access_token),
        timeout=30,
    )
    _raise_for_status(resp)
    data = resp.json()
    if not isinstance(data, dict):
        return None
    name = (data.get("default_branch") or "").strip()
    return name or None


def list_user_repos(
    access_token: str,
    *,
    max_pages: int = 3,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """
    GET /user/repos — repos the token can see (owner / collab / org).

    Returns lightweight dicts: full_name, html_url, private, default_branch.
    Newest-updated first. Caps at max_pages * per_page (default 300).
    """
    if not (access_token or "").strip():
        return []
    out: list[dict[str, Any]] = []
    per = max(1, min(int(per_page), 100))
    pages = max(1, min(int(max_pages), 10))
    for page in range(1, pages + 1):
        resp = requests.get(
            f"{API_BASE}/user/repos",
            headers=_auth_headers(access_token),
            params={
                "per_page": per,
                "page": page,
                "sort": "updated",
                "direction": "desc",
                "affiliation": "owner,collaborator,organization_member",
            },
            timeout=45,
        )
        _raise_for_status(resp)
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            full = (item.get("full_name") or "").strip()
            html = (item.get("html_url") or "").strip()
            if not full or not html:
                continue
            out.append(
                {
                    "full_name": full,
                    "html_url": html.rstrip("/"),
                    "private": bool(item.get("private")),
                    "default_branch": (item.get("default_branch") or "").strip()
                    or None,
                }
            )
        if len(data) < per:
            break
    return out


def list_repo_branches(
    owner: str,
    repo: str,
    *,
    access_token: str | None = None,
    per_page: int = 100,
) -> list[str]:
    """
    GET /repos/{owner}/{repo}/branches — names only.

    Works without token for public repos. Private needs a valid token.
    """
    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{repo}/branches",
        headers=_repo_headers(access_token),
        params={"per_page": max(1, min(per_page, 100))},
        timeout=30,
    )
    _raise_for_status(resp)
    data = resp.json()
    if not isinstance(data, list):
        return []
    names: list[str] = []
    for item in data:
        if isinstance(item, dict):
            n = (item.get("name") or "").strip()
            if n:
                names.append(n)
    return names


def _parse_gh_iso_unix(iso: str) -> int:
    """Parse GitHub ISO-8601 date (…Z) to local unix seconds."""
    s = (iso or "").strip()
    if not s:
        return 0
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0


def _friendly_repo_error(err: GitHubAPIError, *, owner: str, repo: str) -> str:
    """Beginner-friendly Korean message for common commit/repo API failures."""
    if err.status == 404:
        return (
            f"저장소를 찾을 수 없습니다 ({owner}/{repo}).\n"
            "주소가 맞는지 확인하세요. 비공개 저장소는 GitHub 연결이 필요합니다."
        )
    if err.status == 401:
        return (
            "GitHub 연결이 만료되었거나 올바르지 않습니다.\n"
            "위쪽 「GitHub: 연결」에서 다시 연결한 뒤 시도하세요."
        )
    if err.status == 403:
        msg = (err.message or "").lower()
        if "rate limit" in msg or "api rate limit" in msg:
            return (
                "GitHub 요청 한도에 걸렸습니다.\n"
                "잠시 후 다시 시도하거나, GitHub 연결 후 더 넉넉한 한도를 쓰세요."
            )
        return (
            f"이 저장소를 볼 권한이 없습니다 ({owner}/{repo}).\n"
            "비공개 저장소는 GitHub 연결이 필요합니다."
        )
    return str(err)


def list_repo_commits(
    owner: str,
    repo: str,
    *,
    access_token: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> list[CommitInfo]:
    """
    GET /repos/{owner}/{repo}/commits — newest first.

    Works without token for public repos. Private needs a valid token.
    ``file_count`` is 0 here; fill via ``list_remote_changed_files`` on detail.
    """
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    if not owner or not repo:
        raise GitHubAPIError(400, "owner/repo 가 비어 있습니다.")
    per = max(1, min(int(per_page), 100))
    pg = max(1, int(page))
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{repo}/commits",
            headers=_repo_headers(access_token),
            params={"page": pg, "per_page": per},
            timeout=45,
        )
        _raise_for_status(resp)
    except GitHubAPIError as e:
        raise GitHubAPIError(e.status, _friendly_repo_error(e, owner=owner, repo=repo), body=e.body) from e
    data = resp.json()
    if not isinstance(data, list):
        return []
    out: list[CommitInfo] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        sha = (item.get("sha") or "").strip()
        if not sha:
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author_block = (
            commit.get("author") if isinstance(commit.get("author"), dict) else {}
        )
        # Prefer commit.author (git), fall back to GitHub user login
        author = (author_block.get("name") or "").strip()
        if not author:
            gh_user = item.get("author") if isinstance(item.get("author"), dict) else {}
            author = (gh_user.get("login") or "").strip() or "(작성자 없음)"
        unix = _parse_gh_iso_unix(str(author_block.get("date") or ""))
        message = (commit.get("message") or "").strip() or "(메시지 없음)"
        # First line only (subject), like git %s
        subject = message.splitlines()[0].strip() if message else "(메시지 없음)"
        out.append(
            CommitInfo(
                full_hash=sha,
                short_hash=sha[:7],
                author=author,
                unix_time=unix,
                abs_time=format_abs_time(unix) if unix else "",
                message=subject,
                file_count=0,
            )
        )
    return out


_STATUS_KIND = {
    "added": "A",
    "modified": "M",
    "removed": "D",
    "renamed": "R",
    "copied": "C",
    "changed": "M",
}


def list_remote_changed_files(
    owner: str,
    repo: str,
    rev: str,
    *,
    access_token: str | None = None,
) -> list[ChangedFile]:
    """
    GET /repos/{owner}/{repo}/commits/{rev} → files[] as ChangedFile list.
    """
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    rev = (rev or "").strip()
    if not owner or not repo or not rev:
        raise GitHubAPIError(400, "owner/repo/rev 가 비어 있습니다.")
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{repo}/commits/{rev}",
            headers=_repo_headers(access_token),
            timeout=45,
        )
        _raise_for_status(resp)
    except GitHubAPIError as e:
        raise GitHubAPIError(e.status, _friendly_repo_error(e, owner=owner, repo=repo), body=e.body) from e
    data = resp.json()
    if not isinstance(data, dict):
        return []
    files = data.get("files")
    if not isinstance(files, list):
        return []
    out: list[ChangedFile] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = (f.get("filename") or "").strip()
        if not path:
            continue
        status = (f.get("status") or "").strip().lower()
        kind = _STATUS_KIND.get(status, "?")
        out.append(ChangedFile(kind=kind, path=path))
    return out


def compare_remote_commits(
    owner: str,
    repo: str,
    base: str,
    head: str,
    *,
    access_token: str | None = None,
) -> list[ChangedFile]:
    """
    Files that differ between *base* and *head*, in base→head direction:
    A = file *head* has that *base* doesn't, D = file *base* has that *head*
    doesn't, M = present in both, different content. Same direction as
    app.git.history.changed_files_between(folder, base, head). Used to
    preview a revert without cloning: compare(HEAD, target) shows exactly
    what resetting HEAD's tree to target's tree would do.

    GitHub's compare endpoint is BASE...HEAD with **triple-dot** (merge-base)
    semantics, not a literal two-tree diff: it diffs merge_base(base, head)
    against head. Our revert preview always calls this with *head* = an
    older commit the caller wants to revert *to* — i.e. an ancestor of
    *base* — so merge_base(base, head) == head, and a direct base...head
    call would silently diff head against itself and report zero changes.
    We call the API as head...base instead (ancestor first, so its
    merge-base is itself and the diff is meaningful), then flip A/D on the
    result so the returned ChangedFile list still matches the base→head
    contract described above.
    """
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    base = (base or "").strip()
    head = (head or "").strip()
    if not owner or not repo or not base or not head:
        raise GitHubAPIError(400, "owner/repo/base/head 가 비어 있습니다.")
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{repo}/compare/{head}...{base}",
            headers=_repo_headers(access_token),
            timeout=45,
        )
        _raise_for_status(resp)
    except GitHubAPIError as e:
        raise GitHubAPIError(
            e.status, _friendly_repo_error(e, owner=owner, repo=repo), body=e.body
        ) from e
    data = resp.json()
    if not isinstance(data, dict):
        return []
    files = data.get("files")
    if not isinstance(files, list):
        return []
    flip = {"A": "D", "D": "A"}
    out: list[ChangedFile] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = (f.get("filename") or "").strip()
        if not path:
            continue
        status = (f.get("status") or "").strip().lower()
        kind = _STATUS_KIND.get(status, "?")
        kind = flip.get(kind, kind)
        out.append(ChangedFile(kind=kind, path=path))
    return out


def export_remote_commit_snapshot(
    owner: str,
    repo: str,
    rev: str,
    *,
    access_token: str | None = None,
) -> Path:
    """
    Download GET /repos/{owner}/{repo}/zipball/{rev} into a new temp folder.

    Does not touch any local clone. Returns extract directory.
    """
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    rev = (rev or "").strip()
    if not owner or not repo or not rev:
        raise GitHubAPIError(400, "owner/repo/rev 가 비어 있습니다.")
    dest = Path(tempfile.mkdtemp(prefix="CloneUp-view-"))
    zip_path = dest / "_tree.zip"
    try:
        try:
            resp = requests.get(
                f"{API_BASE}/repos/{owner}/{repo}/zipball/{rev}",
                headers=_repo_headers(access_token),
                timeout=180,
                stream=True,
            )
            _raise_for_status(resp)
        except GitHubAPIError as e:
            raise GitHubAPIError(
                e.status, _friendly_repo_error(e, owner=owner, repo=repo), body=e.body
            ) from e
        with open(zip_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    fh.write(chunk)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest)
    except Exception:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
    return dest


def create_repo(
    access_token: str,
    name: str,
    *,
    private: bool = True,
    description: str = "",
    auto_init: bool = False,
) -> dict[str, Any]:
    """
    POST /user/repos

    Requires OAuth scope `repo` for private repos (CloneUp default login).
    Never enable auto_init for CloneUp publish flow: a remote initial commit
    causes non-fast-forward rejection when pushing a fresh local history.
    """
    if auto_init:
        raise ValueError(
            "auto_init must stay False: remote README commit breaks first push "
            "from a new local repo (non-fast-forward)."
        )

    # Omit auto_init entirely (GitHub default is false) — do not send true.
    payload: dict[str, Any] = {
        "name": name,
        "private": bool(private),
        "description": description,
    }
    resp = requests.post(
        f"{API_BASE}/user/repos",
        headers=_auth_headers(access_token),
        json=payload,
        timeout=30,
    )
    _raise_for_status(resp)
    return resp.json()


def delete_repo(access_token: str, owner: str, repo: str) -> None:
    """
    DELETE /repos/{owner}/{repo}

    Needs delete_repo (not granted by `repo` alone for all cases).
    Prefer manual delete on github.com unless this scope is added later.
    """
    resp = requests.delete(
        f"{API_BASE}/repos/{owner}/{repo}",
        headers=_auth_headers(access_token),
        timeout=30,
    )
    if resp.status_code == 204:
        return
    _raise_for_status(resp)
