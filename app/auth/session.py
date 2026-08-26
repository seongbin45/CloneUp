"""Session helpers: validate stored token; never auto-start public Device Flow."""

from __future__ import annotations

from app.auth.device_flow import DeviceFlowError, run_device_flow
from app.auth.token_store import (
    AUTH_KIND_DEVICE,
    AUTH_KIND_PAT,
    SCOPE_UNKNOWN,
    delete_token,
    has_scope,
    is_scope_unknown,
    load_auth_kind,
    load_connected_at_raw,
    load_scope,
    load_token,
    format_scopes_display,
    normalize_scope_string,
    parse_oauth_scopes,
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
    pretty = format_scopes_display(current_scopes)
    scopes = pretty or (current_scopes or "").strip() or "(없음)"
    return (
        f"{MISSING_REPO_MARKER}\n"
        "\n"
        "왜 이런가요?\n"
        "CloneUp이 폴더를 GitHub에 올리고 받으려면\n"
        "「repo」(저장소) 권한이 있는 키가 필요합니다.\n"
        "지금 붙여 넣은 키에는 그 권한이 없습니다.\n"
        "\n"
        "차근차근 다시 하기\n"
        "A) 같은 키(classic)를 쓰는 경우\n"
        "  1) GitHub → Settings → Developer settings → Tokens (classic)\n"
        "  2) 해당 키를 열어 「repo」에 체크 후 저장\n"
        "  3) 설정 → 「권한 다시 확인」 또는 「GitHub: 연결」\n"
        "B) 키를 새로 만드는 경우\n"
        "  1) 「새 키 만들기」(Tokens classic)\n"
        "  2) Expiration — 90일 또는 없음 권장\n"
        "  3) Select scopes에서 「repo」(Full control of private repositories) ✓\n"
        "  4) Generate token → 초록 키 전체 복사 → 「GitHub: 연결」에 붙여 넣기\n"
        "\n"
        f"이 키에 있던 권한: {scopes}\n"
        "※ classic 키는 웹에서 권한(scope)을 바꿀 수 있습니다. "
        "바꾼 뒤에는 앱에서 「권한 다시 확인」을 눌러 주세요."
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


def _save_scope_only(token: str, scope: str, *, auth_kind: str | None = None) -> None:
    """
    Update keyring scope (and optional auth_kind) without resetting connect age.

    Scope backfill from GET /user must not make the key look brand-new every time.
    """
    prev_at = load_connected_at_raw()
    kwargs: dict = {}
    if auth_kind is not None:
        kwargs["auth_kind"] = auth_kind
    if prev_at:
        kwargs["connected_at"] = prev_at
    save_token(token, scope, **kwargs)


def apply_oauth_scopes_from_user(token: str, user: dict) -> str:
    """
    Persist classic scopes from GET /user ``_oauth_scopes`` (X-OAuth-Scopes).

    Returns the scope string now stored (may be ``SCOPE_UNKNOWN``).
    Does not invent ``repo`` when the header is empty (M3 / fine-grained).
    """
    header = user.get("_oauth_scopes")
    current = load_scope()

    if header is None:
        # Header omitted entirely — leave stored value; unknown if empty.
        if current is None or (current or "").strip() == "":
            _save_scope_only(token, SCOPE_UNKNOWN)
            print(f"  scope → {SCOPE_UNKNOWN!r} (header omitted)")
            return SCOPE_UNKNOWN
        return (current or "").strip()

    header_stripped = (header or "").strip()
    if header_stripped:
        normalized = normalize_scope_string(header_stripped)
        if current != normalized:
            _save_scope_only(token, normalized)
            print(f"  scope from X-OAuth-Scopes: {normalized!r}")
        return normalized

    # Empty header: fine-grained PAT (or rare omit). Never invent "repo" (M3).
    # If we already stored a classic list, keep it — do not wipe on empty header
    # (revoke/regenerate is 401; scope edits on the web show up on next refresh).
    if current is None or (current or "").strip() == "" or is_scope_unknown(current):
        if current != SCOPE_UNKNOWN:
            _save_scope_only(token, SCOPE_UNKNOWN)
            print(f"  scope backfill → {SCOPE_UNKNOWN!r} (header empty)")
        return SCOPE_UNKNOWN
    return (current or "").strip()

def refresh_scopes_from_github(
    *,
    timeout: float = 12,
) -> tuple[str | None, dict | None]:
    """
    Live-refresh stored scopes via GET /user (for Settings display).

    Returns ``(scope_now, user_json)`` or ``(None, None)`` if no token /
    network/API failure (caller keeps showing last keyring value).
    On 401, deletes the token and returns ``(None, None)``.

    Uses a shorter HTTP timeout than publish/sync so opening Settings does
    not block the UI for a full 30s on a dead network.
    """
    token = load_token()
    if not token:
        return None, None
    try:
        user = get_authenticated_user(token, timeout=timeout)
    except GitHubAPIError as e:
        if e.status == 401:
            print("권한 새로고침: 토큰 무효(401) → keyring 삭제")
            delete_token()
            return None, None
        print(f"권한 새로고침 실패: {e}")
        return load_scope(), None
    except Exception as e:  # network / timeout etc.
        print(f"권한 새로고침 실패: {e}")
        return load_scope(), None

    scope = apply_oauth_scopes_from_user(token, user)
    return scope, user


def login_with_pat(
    token: str, *, expires_at: str | None = None
) -> tuple[str, dict]:
    """
    Validate a user-supplied Personal Access Token and store it.

    Does **not** use CloneUp's OAuth client_id. User creates the token on
    github.com; malware cannot complete this without the user's token string.

    ``expires_at``: ISO-8601 UTC or ``none`` from page scrape; if missing,
    best-effort API lookup may fill it for fine-grained tokens.
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

    # GitHub X-OAuth-Scopes is often comma-separated: "repo, workflow"
    # (docs + live API). Space-only split misreads "repo," as the name.
    header_scopes = (user.get("_oauth_scopes") or "").strip()
    want = get_github_scopes()
    needed = [s for s in want.split() if s]

    if header_scopes:
        parts = set(parse_oauth_scopes(header_scopes))
        display = normalize_scope_string(header_scopes) or header_scopes
        if "repo" in needed and "repo" not in parts:
            raise AuthError(format_missing_repo_scope_error(display))
        if needed and "repo" not in parts:
            missing = [
                s
                for s in needed
                if s not in parts and not (s == "public_repo" and "repo" in parts)
            ]
            if missing:
                raise AuthError(format_missing_repo_scope_error(display))
        store_scope = normalize_scope_string(header_scopes)
    else:
        # Fine-grained PAT often omits X-OAuth-Scopes — never invent "repo" (M3).
        print(
            "X-OAuth-Scopes 비어 있음 → "
            f"scope={SCOPE_UNKNOWN!r} 저장 (세분 키 가능 · 권한은 작업 시 확인)"
        )
        store_scope = SCOPE_UNKNOWN

    exp = (expires_at or "").strip() or None
    if not exp:
        exp = _lookup_expires_at_via_api(cleaned, user=user)
    save_token(
        cleaned, store_scope, auth_kind=AUTH_KIND_PAT, expires_at=exp or ""
    )
    print(f"키 저장됨 (masked): {mask_token(cleaned)}")
    print(f"granted scope (stored): {store_scope!r}")
    print(f"auth kind: {AUTH_KIND_PAT}")
    print(f"expires_at: {exp!r}")
    print(f"user: {user.get('login')!r}")
    user = dict(user)
    user["_expires_at"] = exp
    return cleaned, user


def _lookup_expires_at_via_api(token: str, *, user: dict | None = None) -> str | None:
    """Best-effort: fine-grained token list may expose expires_at."""
    import requests

    from app.auth.token_expiry import parse_expires_label

    _ = user
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Fine-grained personal access tokens (may 403 for classic ghp_)
    try:
        r = requests.get(
            "https://api.github.com/user/personal-access-tokens",
            headers=headers,
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("tokens") or []
            best = None
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or it.get("token_name") or "")
                if name.startswith("CloneUp"):
                    best = it
                    break
                if best is None:
                    best = it
            if isinstance(best, dict):
                exp = best.get("expires_at") or best.get("expiration")
                if exp in (None, "", "null"):
                    return "none"
                if isinstance(exp, str):
                    parsed = parse_expires_label(exp, exp)
                    return parsed or exp
        else:
            print(f"만료일 API 조회 생략 (HTTP {r.status_code})")
    except Exception as e:
        print(f"만료일 API 조회 실패: {e}")
    return None


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

    Always validates with GET /user **before** the classic-scope gate, so a
    keyring scope that is stale relative to GitHub is refreshed first.
    Settings and later UI then see the same stored list.

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
        apply_oauth_scopes_from_user(token, user)
        return token, user

    want = scopes if scopes is not None else get_github_scopes()
    needed = [s for s in want.split() if s]

    token = load_token()
    if not token:
        print("저장된 토큰 없음 → 자동 Device Flow 하지 않음")
        raise AuthError(LOGIN_REQUIRED_MSG)

    print("keyring 토큰 검증 중…")
    print(f"  stored scope (before refresh): {load_scope()!r}")
    print(f"  auth kind: {load_auth_kind()!r}")
    try:
        user = get_authenticated_user(token)
    except GitHubAPIError as e:
        if e.status != 401:
            raise AuthError(f"GET /user 실패: {e}") from e
        print("토큰 무효(401) → keyring 삭제 (자동 재로그인 없음) — 만료·취소 가능")
        delete_token()
        raise AuthError(TOKEN_EXPIRED_MSG) from e

    # Refresh keyring from live X-OAuth-Scopes *before* the scope gate.
    # Old order gated on stale keyring and never called the API when scope
    # looked too narrow — so GitHub-side changes never reached Settings.
    stored = apply_oauth_scopes_from_user(token, user)
    print(f"  stored scope (after refresh): {stored!r}")

    # Only enforce when classic scopes are known. Fine-grained / unknown →
    # allow through; API/git will fail with a clear error if rights lack.
    if needed and scopes_known() and not all(has_scope(s) for s in needed):
        print(f"  필요 권한 {want!r} 보다 좁음 → 재연결 안내")
        raise AuthError(format_missing_repo_scope_error(stored or load_scope() or ""))

    return token, user
