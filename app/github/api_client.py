"""Minimal GitHub REST helpers (spike)."""

from __future__ import annotations

from typing import Any

import requests

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
    headers = {
        **DEFAULT_HEADERS,
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{repo}/branches",
        headers=headers,
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


def create_repo(
    access_token: str,
    name: str,
    *,
    private: bool = False,
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
