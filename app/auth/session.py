"""Session helpers: validate stored token; never auto-start public Device Flow."""

from __future__ import annotations

from app.auth.device_flow import DeviceFlowError, run_device_flow
from app.auth.token_store import (
    AUTH_KIND_DEVICE,
    AUTH_KIND_PAT,
    SCOPE_UNKNOWN,
    delete_token,
    has_scope,
    load_auth_kind,
    load_scope,
    load_token,
    save_token,
    scopes_known,
)
from app.config import (
    get_github_client_id,
    get_github_scopes,
    is_device_flow_allowed,
)
from app.github.api_client import GitHubAPIError, get_authenticated_user
from app.util.log_mask import mask_token

# Shown whenever a worker needs auth but keyring is empty / invalid.
LOGIN_REQUIRED_MSG = (
    "GitHub 연결이 필요합니다.\n"
    "창 위쪽 「GitHub: 연결」을 누른 뒤, "
    "GitHub에서 만든 키를 붙여 넣으세요."
)

TOKEN_EXPIRED_MSG = (
    "저장된 키가 만료되었거나 취소·삭제되었습니다.\n"
    "GitHub에서 새 키를 만들고 (저장소 권한 · 만료일 확인),\n"
    "창 위쪽 「GitHub: 연결」에서 다시 붙여 넣으세요."
)

# Detectable marker for friendly UI dialog (see show_missing_repo_help).
MISSING_REPO_MARKER = "저장소(repo) 권한이 없습니다"


def format_missing_repo_scope_error(current_scopes: str) -> str:
    """Beginner-oriented AuthError text when classic PAT lacks ``repo``."""
    scopes = (current_scopes or "").strip() or "(없음)"
    return (
        f"{MISSING_REPO_MARKER}\n"
        "\n"
        "왜 이런가요?\n"
        "CloneUp이 폴더를 GitHub에 올리고 받으려면\n"
        "「repo」(저장소) 권한이 있는 키가 필요합니다.\n"
        "지금 붙여 넣은 키에는 그 권한이 없습니다.\n"
        "\n"
        "차근차근 다시 만들기\n"
        "1) 「새 키 만들기」로 GitHub 페이지를 엽니다\n"
        "2) Expiration(만료일) — 90일 또는 없음 권장\n"
        "3) 권한 목록에서 repo 앞에 체크 ✓\n"
        "4) Generate token(토큰 생성) 누르기\n"
        "5) 초록색으로 보이는 긴 키 전체를 복사\n"
        "6) 「GitHub: 로그인」에서 그 새 키를 붙여 넣기\n"
        "\n"
        f"이 키에 있던 권한: {scopes}\n"
        "※ 예전 키는 권한을 나중에 추가할 수 없습니다. 새 키를 만드세요."
    )


class AuthError(Exception):
    """Could not obtain a working GitHub session."""


def login_device_flow(
    *,
    open_browser: bool = True,
    copy_code: bool = True,
    scopes: str | None = None,
    on_user_code=None,
    should_cancel=None,
) -> str:
    """
    Device Flow — **disabled for end users** (is_device_flow_allowed).

    Kept for maintainer opt-in only. Public client_id can be abused by malware
    that polls the same device grant the user just approved.
    """
    if not is_device_flow_allowed():
        raise AuthError(
            "브라우저(장치 코드) 로그인은 보안상 꺼져 있습니다.\n"
            "「GitHub: 로그인」에서 키를 붙여 넣어 연결하세요."
        )

    client_id = get_github_client_id()
    scope = scopes if scopes is not None else get_github_scopes()
    try:
        token_resp = run_device_flow(
            client_id,
            scope=scope,
            open_browser=open_browser,
            copy_code=copy_code,
            on_user_code=on_user_code,
            should_cancel=should_cancel,
        )
    except DeviceFlowError as e:
        raise AuthError(str(e)) from e

    save_token(
        token_resp.access_token,
        token_resp.scope,
        auth_kind=AUTH_KIND_DEVICE,
    )
    print(f"토큰 저장됨 (masked): {mask_token(token_resp.access_token)}")
    print(f"granted scope (stored): {token_resp.scope!r}")
    print(f"auth kind: {AUTH_KIND_DEVICE}")
    return token_resp.access_token


def login_with_pat(token: str) -> tuple[str, dict]:
    """
    Validate a user-supplied Personal Access Token and store it.

    Does **not** use CloneUp's OAuth client_id. User creates the token on
    github.com; malware cannot complete this without the user's token string.
    """
    cleaned = (token or "").strip()
    if not cleaned:
        raise AuthError("키가 비어 있습니다. GitHub에서 만든 키를 붙여 넣으세요.")
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    if len(cleaned) < 20:
        raise AuthError("키가 너무 짧습니다. 전체를 복사했는지 확인하세요.")

    print("키 검증 중 (GET /user)…")
    try:
        user = get_authenticated_user(cleaned)
    except GitHubAPIError as e:
        if e.status == 401:
            raise AuthError(
                "키가 올바르지 않거나 이미 만료·취소되었습니다.\n"
                "GitHub에서 새 키를 만드세요.\n"
                "· 권한: repo (저장소)\n"
                "· 만료일: 너무 짧으면 자주 다시 만들어야 합니다 "
                "(초보 권장: 90일 또는 만료 없음)"
            ) from e
        raise AuthError(f"GitHub 확인 실패: {e}") from e

    header_scopes = (user.get("_oauth_scopes") or "").strip()
    want = get_github_scopes()
    needed = [s for s in want.split() if s]

    if header_scopes:
        parts = set(header_scopes.split())
        if "repo" in needed and "repo" not in parts:
            raise AuthError(format_missing_repo_scope_error(header_scopes))
        if needed and "repo" not in parts:
            missing = [
                s
                for s in needed
                if s not in parts and not (s == "public_repo" and "repo" in parts)
            ]
            if missing:
                raise AuthError(format_missing_repo_scope_error(header_scopes))
        store_scope = header_scopes
    else:
        # Fine-grained PAT often omits X-OAuth-Scopes — never invent "repo" (M3).
        print(
            "X-OAuth-Scopes 비어 있음 → "
            f"scope={SCOPE_UNKNOWN!r} 저장 (세분 키 가능 · 권한은 작업 시 확인)"
        )
        store_scope = SCOPE_UNKNOWN

    save_token(cleaned, store_scope, auth_kind=AUTH_KIND_PAT)
    print(f"키 저장됨 (masked): {mask_token(cleaned)}")
    print(f"granted scope (stored): {store_scope!r}")
    print(f"auth kind: {AUTH_KIND_PAT}")
    print(f"user: {user.get('login')!r}")
    return cleaned, user


def ensure_valid_token(
    *,
    force_login: bool = False,
    open_browser: bool = True,
    copy_code: bool = True,
    scopes: str | None = None,
    on_user_code=None,
    should_cancel=None,
) -> tuple[str, dict]:
    """
    Return (access_token, user_json) from **existing** keyring token only.

    Security: does **not** auto-start Device Flow. Missing/invalid tokens raise
    AuthError(LOGIN_REQUIRED_MSG) so the UI can open PAT login.

    ``force_login=True`` only runs Device Flow when ``is_device_flow_allowed()``
    (maintainer opt-in). Otherwise raises AuthError.
    """
    login_kw = dict(
        open_browser=open_browser,
        copy_code=copy_code,
        on_user_code=on_user_code,
        should_cancel=should_cancel,
    )

    if force_login:
        if not is_device_flow_allowed():
            raise AuthError(LOGIN_REQUIRED_MSG)
        token = login_device_flow(scopes=scopes, **login_kw)
        user = get_authenticated_user(token)
        return token, user

    want = scopes if scopes is not None else get_github_scopes()
    needed = [s for s in want.split() if s]

    token = load_token()
    if not token:
        print("저장된 토큰 없음 → 자동 Device Flow 하지 않음")
        raise AuthError(LOGIN_REQUIRED_MSG)

    # Only enforce scope gate when classic scopes are known. Fine-grained /
    # unknown → allow through; API/git will fail with a clear error if rights lack.
    if needed and scopes_known() and not all(has_scope(s) for s in needed):
        # Do not silently re-auth via public client_id.
        print(
            f"저장된 scope {load_scope()!r} 가 필요 권한 {want!r} 보다 좁음"
        )
        raise AuthError(format_missing_repo_scope_error(load_scope() or ""))

    print("keyring 토큰 검증 중…")
    print(f"  stored scope: {load_scope()!r}")
    print(f"  auth kind: {load_auth_kind()!r}")
    try:
        user = get_authenticated_user(token)
    except GitHubAPIError as e:
        if e.status != 401:
            raise AuthError(f"GET /user 실패: {e}") from e
        print("토큰 무효(401) → keyring 삭제 (자동 재로그인 없음) — 만료·취소 가능")
        delete_token()
        raise AuthError(TOKEN_EXPIRED_MSG) from e

    # Backfill / refresh classic scopes from API when present.
    header_scopes = user.get("_oauth_scopes")
    if header_scopes is not None:
        header_stripped = (header_scopes or "").strip()
        current = load_scope()
        if header_stripped:
            if current != header_stripped:
                save_token(token, header_stripped)
                print(f"  scope from X-OAuth-Scopes: {header_stripped!r}")
            if needed and not all(has_scope(s) for s in needed):
                raise AuthError(
                    format_missing_repo_scope_error(header_stripped)
                )
        elif current is None or (current or "").strip() == "":
            # Empty header + no stored scope → mark unknown (not invent repo)
            save_token(token, SCOPE_UNKNOWN)
            print(f"  scope backfill → {SCOPE_UNKNOWN!r} (header empty)")

    return token, user
