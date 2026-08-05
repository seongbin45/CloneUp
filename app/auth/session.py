"""Session helpers: valid token or automatic re-login on 401."""

from __future__ import annotations

from app.auth.device_flow import DeviceFlowError, run_device_flow
from app.auth.token_store import (
    delete_token,
    has_scope,
    load_scope,
    load_token,
    save_token,
)
from app.config import get_github_client_id, get_github_scopes
from app.github.api_client import GitHubAPIError, get_authenticated_user
from app.util.log_mask import mask_token


class AuthError(Exception):
    """Could not obtain a working GitHub session."""


def login_device_flow(
    *,
    open_browser: bool = True,
    copy_code: bool = True,
    scopes: str | None = None,
    on_user_code=None,
) -> str:
    """Run Device Flow, store token+scope, return access token."""
    client_id = get_github_client_id()
    scope = scopes if scopes is not None else get_github_scopes()
    try:
        token_resp = run_device_flow(
            client_id,
            scope=scope,
            open_browser=open_browser,
            copy_code=copy_code,
            on_user_code=on_user_code,
        )
    except DeviceFlowError as e:
        raise AuthError(str(e)) from e

    save_token(token_resp.access_token, token_resp.scope)
    print(f"토큰 저장됨 (masked): {mask_token(token_resp.access_token)}")
    print(f"granted scope (stored): {token_resp.scope!r}")
    return token_resp.access_token


def ensure_valid_token(
    *,
    force_login: bool = False,
    open_browser: bool = True,
    copy_code: bool = True,
    scopes: str | None = None,
    on_user_code=None,
) -> tuple[str, dict]:
    """
    Return (access_token, user_json).

    If keyring has a token, validate with GET /user.
    On 401: delete keyring entry and run Device Flow again (no --force needed).
    """
    login_kw = dict(
        open_browser=open_browser,
        copy_code=copy_code,
        on_user_code=on_user_code,
    )

    if force_login:
        delete_token()
        token = login_device_flow(scopes=scopes, **login_kw)
        user = get_authenticated_user(token)
        return token, user

    want = scopes if scopes is not None else get_github_scopes()
    # If stored grant is narrower than app default (e.g. old public_repo only),
    # re-auth so private create works without a separate UX path.
    needed = [s for s in want.split() if s]
    if load_token() and needed and not all(has_scope(s) for s in needed):
        print(
            f"저장된 scope {load_scope()!r} 가 필요 권한 {want!r} 보다 좁음 → 재로그인"
        )
        delete_token()
        token = login_device_flow(scopes=want, **login_kw)
        user = get_authenticated_user(token)
        return token, user

    token = load_token()
    if not token:
        print("저장된 토큰 없음 → Device Flow 시작")
        token = login_device_flow(scopes=scopes, **login_kw)
        user = get_authenticated_user(token)
        return token, user

    print("keyring 토큰 검증 중…")
    print(f"  stored scope: {load_scope()!r}")
    try:
        user = get_authenticated_user(token)
    except GitHubAPIError as e:
        if e.status != 401:
            raise AuthError(f"GET /user 실패: {e}") from e
        print("토큰 무효(401) → keyring 삭제 후 재로그인")
        delete_token()
        token = login_device_flow(scopes=scopes, **login_kw)
        try:
            user = get_authenticated_user(token)
        except GitHubAPIError as e2:
            raise AuthError(f"재로그인 후에도 GET /user 실패: {e2}") from e2
        return token, user

    # Backfill scope from API header if keyring only had a token (pre-scope store).
    header_scopes = user.get("_oauth_scopes")
    if header_scopes is not None and load_scope() is None:
        save_token(token, header_scopes)
        print(f"  scope backfill from X-OAuth-Scopes: {header_scopes!r}")
        # After backfill, check again — old public_repo may still be too narrow.
        if needed and not all(has_scope(s) for s in needed):
            print(
                f"backfill 후에도 scope {load_scope()!r} 부족 → 재로그인 ({want!r})"
            )
            delete_token()
            token = login_device_flow(scopes=want, **login_kw)
            user = get_authenticated_user(token)
            return token, user

    return token, user
