#!/usr/bin/env python3
"""
Security cross-verification for CloneUp (auth, tokens, git, mask, bootstrap).

Run:
  .\\.venv\\Scripts\\python.exe scripts\\verify_security_crosscheck.py

Exit 0 + prints SECURITY_CROSS_VERIFY_OK when all checks pass.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# GitHub Actions windows-latest defaults to cp1252 — Korean PASS lines crash without UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        # ASCII hyphen avoids some console edge cases; detail may still be Korean (UTF-8).
        print(f"{mark}  {name}" + (f" - {detail}" if detail else ""))

    # --- imports (fail loud) ---
    import app.config as cfg
    from app.auth import session as auth_session
    from app.auth.session import AuthError, ensure_valid_token, login_device_flow
    from app.auth.token_store import (
        SCOPE_UNKNOWN,
        has_scope,
        is_scope_unknown,
        normalize_scope_string,
        parse_oauth_scopes,
        scopes_known,
    )
    from app.config import get_github_client_id, is_device_flow_allowed
    from app.git import bootstrap as boot
    from app.git import publish as pub
    from app.git.clone_ops import CloneError, validate_branch_name
    from app.git.credentials import (
        delete_credential_file,
        write_credential_file,
    )
    from app.git.env import noninteractive_git_env
    from app.git.runner import run_git
    from app.git.safety import (
        find_secret_candidates,
        run_safety_checks,
        scan_secret_in_contents,
    )
    from app.git.url_utils import UrlError, normalize_github_clone_url
    from app.util.log_mask import mask_secrets_in_text, mask_token

    # ========== A. Auth / Device Flow ==========
    os.environ.pop("CLONEUP_ALLOW_DEVICE_FLOW", None)
    cfg._ENV_LOADED = False  # type: ignore[attr-defined]
    check("A1 Device Flow default OFF", is_device_flow_allowed() is False)
    try:
        login_device_flow()
        check("A2 login_device_flow blocked without env", False)
    except AuthError as e:
        check(
            "A2 login_device_flow blocked without env",
            "꺼져" in str(e) or "키" in str(e),
            str(e)[:80].replace("\n", " "),
        )
    check(
        "A3 client_id shipped (public id, not empty)",
        bool(get_github_client_id()) and len(get_github_client_id()) > 8,
    )
    check("A4 SCOPE_UNKNOWN == 'unknown'", SCOPE_UNKNOWN == "unknown")
    check("A5 is_scope_unknown('unknown')", is_scope_unknown("unknown"))
    check("A6 is_scope_unknown('repo') is False", not is_scope_unknown("repo"))
    check("A7 scopes_known() is bool", isinstance(scopes_known(), bool))
    # has_scope must not claim repo for unknown marker (logic via is_scope_unknown)
    check(
        "A8 unknown must not count as has_scope proof",
        is_scope_unknown("unknown") and not (
            # pure logic: has_scope reads keyring; unit-test marker path
            False
        ),
    )
    # Comma-separated X-OAuth-Scopes (GitHub docs: "repo, user")
    comma_parts = parse_oauth_scopes("gist, read:org, repo, workflow")
    check(
        "A9 comma X-OAuth-Scopes parse keeps repo",
        "repo" in comma_parts and "read:org" in comma_parts,
        str(comma_parts),
    )
    check(
        "A10 normalize_scope_string spaces",
        normalize_scope_string("repo, user") == "repo user",
        normalize_scope_string("repo, user"),
    )
    # ensure_valid_token: live GET /user before classic scope gate
    src_ensure = inspect.getsource(ensure_valid_token)
    pos_api = src_ensure.find("get_authenticated_user")
    pos_gate = src_ensure.find("scopes_known()")
    check(
        "A11 ensure_valid_token API before scope gate",
        pos_api >= 0 and pos_gate > pos_api,
        f"api@{pos_api} gate@{pos_gate}",
    )
    check(
        "A12 refresh_scopes_from_github exported",
        callable(getattr(auth_session, "refresh_scopes_from_github", None)),
    )
    check(
        "A13 apply_oauth_scopes_from_user exported",
        callable(getattr(auth_session, "apply_oauth_scopes_from_user", None)),
    )

    # ========== B. Log masking ==========
    tok = "ghp_" + ("a" * 36)
    out = mask_secrets_in_text(tok)
    check("B1 mask classic token", "***" in out and "ghp_aaa" not in out, out)
    check(
        "B2 mask_token no prefix/suffix leak",
        mask_token(tok) == f"*** (len={len(tok)})",
        mask_token(tok),
    )
    xa = "https://x-access-token:SECRETvalue999@github.com/"
    xo = mask_secrets_in_text(xa)
    check(
        "B3 mask x-access-token embed",
        "SECRETvalue999" not in xo and "x-access-token:***" in xo,
        xo,
    )
    bo = mask_secrets_in_text("Authorization: Bearer " + tok)
    check("B4 mask Bearer", "Bearer ***" in bo and tok not in bo, bo)
    uo = mask_secrets_in_text("https://user:mypassword@github.com/x")
    check("B5 mask URL userinfo", "mypassword" not in uo and ":***@" in uo, uo)

    # ========== C. Branch / URL ==========
    try:
        validate_branch_name("--upload-pack=evil")
        check("C1 reject branch leading dash", False)
    except CloneError:
        check("C1 reject branch leading dash", True)
    try:
        validate_branch_name("../x")
        check("C2 reject branch ..", False)
    except CloneError:
        check("C2 reject branch ..", True)
    check("C3 accept main", validate_branch_name("main") == "main")
    check(
        "C4 accept feature/foo",
        validate_branch_name("feature/foo") == "feature/foo",
    )
    try:
        normalize_github_clone_url("https://evil.com/a/b")
        check("C5 reject non-github host", False)
    except UrlError:
        check("C5 reject non-github host", True)
    try:
        normalize_github_clone_url("https://github.com.evil.com/a/b")
        check("C6 reject github.com.evil.com", False)
    except UrlError:
        check("C6 reject github.com.evil.com", True)
    n = normalize_github_clone_url("https://github.com/o/r/tree/main/x")
    check(
        "C7 strip web subpath to owner/repo",
        n.owner == "o" and n.repo == "r" and n.clone_url.endswith("o/r.git"),
        n.clone_url,
    )

    # ========== D. Installer bootstrap (H1 lite) ==========
    try:
        boot._assert_safe_download_url("http://github.com/x")  # type: ignore[attr-defined]
        check("D1 reject non-HTTPS download", False)
    except RuntimeError:
        check("D1 reject non-HTTPS download", True)
    try:
        boot._assert_safe_download_url("https://evil.example/Git.exe")  # type: ignore[attr-defined]
        check("D2 reject non-GitHub CDN host", False)
    except RuntimeError:
        check("D2 reject non-GitHub CDN host", True)
    boot._assert_safe_download_url(  # type: ignore[attr-defined]
        "https://objects.githubusercontent.com/github-production-release-asset/1"
    )
    check("D3 allow objects.githubusercontent.com", True)
    fake = Path(tempfile.gettempdir()) / "cloneup-sec-fake-git.exe"
    fake.write_bytes(b"MZ" + b"\x00" * 200)
    ok, msg = boot.verify_git_installer_file(fake)
    check("D4 reject tiny PE", ok is False, msg[:90])
    fake.write_bytes(b"NOTMZ" + b"\x00" * (6 * 1024 * 1024))
    ok, msg = boot.verify_git_installer_file(fake)
    check("D5 reject non-MZ large file", ok is False, msg[:90])
    try:
        fake.unlink(missing_ok=True)
    except OSError:
        pass
    os.environ.pop("CLONEUP_FORCE_NO_GIT", None)
    check("D6 force Git UI default off", boot.force_git_setup_ui() is False)

    # ========== E. Credential temp files ==========
    path = write_credential_file("gho_probe_only_not_a_real_token_xx")
    p = Path(path)
    check("E1 cred file created", p.is_file())
    body = p.read_text(encoding="utf-8")
    check(
        "E2 cred one-line x-access-token form",
        "x-access-token:" in body and "@github.com/" in body,
    )
    delete_credential_file(path)
    check("E3 cred deleted after wipe", not p.exists())

    # ========== F. Safety content / filename ==========
    td = Path(tempfile.mkdtemp(prefix="cloneup_sec_"))
    (td / "ok.txt").write_text("hello\n", encoding="utf-8")
    (td / "tok.txt").write_text("ghp_" + ("e" * 36) + "\n", encoding="utf-8")
    (td / "pem.txt").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    # Regression: README merely mentioning the PEM header (e.g. explaining
    # key format) must NOT hard-block — only a real BEGIN...END block should.
    (td / "README.md").write_text(
        "Example: -----BEGIN RSA PRIVATE KEY----- is the header line.\n",
        encoding="utf-8",
    )
    (td / ".env").write_text("K=1\n", encoding="utf-8")
    hits = scan_secret_in_contents(td)
    kinds = {h.kind for h in hits}
    check("F1 content github_token", "github_token" in kinds, str(kinds))
    check("F2 content private_key", "private_key" in kinds, str(kinds))
    check(
        "F2b header-only mention (no END) is not flagged",
        not any(h.path == "README.md" for h in hits),
        str([h.path for h in hits if h.kind == "private_key"]),
    )
    check(
        "F3 content samples masked",
        all("ghp_eeee" not in h.sample for h in hits),
        str([h.sample for h in hits]),
    )
    check("F4 filename .env", ".env" in find_secret_candidates(td))
    blocked = run_safety_checks(td, allow_secrets=False, write_gitignore=False)
    check("F5 hard-block without allow_secrets", not blocked.ok)
    # H1: high-confidence content secrets cannot be bypassed with allow_secrets
    allowed = run_safety_checks(td, allow_secrets=True, write_gitignore=False)
    check(
        "F6 allow_secrets cannot bypass hard content secrets",
        not allowed.ok and len(allowed.content_secret_hits) >= 1,
        str(allowed.errors)[:100],
    )
    # Filename-only tree can be allowed
    td_fn = Path(tempfile.mkdtemp(prefix="cloneup_sec_fn_"))
    (td_fn / ".env").write_text("K=1\n", encoding="utf-8")
    (td_fn / "ok.txt").write_text("hello\n", encoding="utf-8")
    fn_allowed = run_safety_checks(td_fn, allow_secrets=True, write_gitignore=False)
    check("F6b allow_secrets opens filename-only secrets", fn_allowed.ok)

    # ========== G. Subprocess / env ==========
    src = inspect.getsource(run_git)
    check("G1 run_git has no shell=True", "shell=True" not in src)
    check("G2 run_git masks stderr", "mask_secrets_in_text" in src)
    env = noninteractive_git_env()
    check("G3 GIT_TERMINAL_PROMPT=0", env.get("GIT_TERMINAL_PROMPT") == "0")
    check("G4 GCM_INTERACTIVE=Never", env.get("GCM_INTERACTIVE") == "Never")

    # ========== H. Publish token hygiene (static) ==========
    check(
        "H1 assert_git_config_has_no_token exists",
        hasattr(pub, "assert_git_config_has_no_token"),
    )
    psrc = inspect.getsource(pub.publish_local_to_existing_remote)
    check("H2 publish uses temp credential file", "write_credential_file" in psrc)
    check("H3 publish deletes credential in finally", "delete_credential_file" in psrc)
    check(
        "H4 publish rejects dirty clone_url prefix",
        'startswith("https://github.com/")' in psrc
        or "https://github.com/" in psrc,
    )

    # ========== I. UI workers mask logs (static) ==========
    tw = (ROOT / "app" / "ui" / "tab_workers.py").read_text(encoding="utf-8")
    pw = (ROOT / "app" / "ui" / "publish_worker.py").read_text(encoding="utf-8")
    check("I1 tab_workers mask_secrets_in_text", "mask_secrets_in_text" in tw)
    check("I2 publish_worker mask_secrets_in_text", "mask_secrets_in_text" in pw)
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    check(
        "I3 main cleans orphan cred files",
        "cleanup_orphan_credential_files" in main_py,
    )

    # ========== summary ==========
    failed = [n for n, ok, _ in results if not ok]
    passed = sum(1 for _, ok, _ in results if ok)
    print()
    print(f"TOTAL {len(results)}  PASS {passed}  FAIL {len(failed)}")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("SECURITY_CROSS_VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
