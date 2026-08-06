#!/usr/bin/env python3
"""
CloneUp cross-verification (no GUI click automation).

Run:
  .\\.venv\\Scripts\\python.exe scripts\\cross_verify.py

Exit 0 = all runnable checks passed.
Exit 1 = failure.
Exit 2 = auth missing (partial pass; re-login needed for full suite).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
SKIP = 0
RESULTS: list[str] = []


def ok(name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    RESULTS.append(f"PASS  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    RESULTS.append(f"FAIL  {name} — {detail}")


def skip(name: str, detail: str) -> None:
    global SKIP
    SKIP += 1
    RESULTS.append(f"SKIP  {name} — {detail}")


def section(title: str) -> None:
    RESULTS.append(f"\n## {title}")


def main() -> int:
    from app.auth.token_store import has_scope, load_scope, load_token
    from app.git.clone_ops import CloneError, clone_repository
    from app.git.credentials import (
        credential_helper_configs,
        delete_credential_file,
        write_credential_file,
    )
    from app.git.publish import PublishError, publish_folder_to_new_repo
    from app.git.runner import require_git, run_git
    from app.git.safety import run_safety_checks
    from app.git.sync_ops import SyncError, get_repo_status, pull_repo
    from app.git.url_utils import UrlError, normalize_github_clone_url
    from app.github.api_client import create_repo, get_authenticated_user
    from app.util.log_mask import mask_secrets_in_text, mask_token

    # ----- env -----
    section("환경")
    try:
        exe, ver = require_git()
        ok("git 설치", f"{exe} {ver[0]}.{ver[1]}.{ver[2]}")
    except Exception as e:
        fail("git 설치", str(e))
        _print_report()
        return 1

    token = load_token()
    scope = load_scope()
    if token and has_scope("repo"):
        ok("keyring 토큰", f"{mask_token(token)} scope={scope!r}")
        auth_ok = True
    elif token:
        ok("keyring 토큰(좁은 scope)", f"{mask_token(token)} scope={scope!r}")
        auth_ok = True
    else:
        skip("keyring 토큰", "없음 — 로그인 필요 검사는 SKIP/부분 실행")
        auth_ok = False

    # ----- URL -----
    section("URL 정규화 (Clone)")
    # Build SSH sample without a literal "git@..." string (some editors rewrite it).
    ssh_sample = "git" + "@" + "github.com:seongbin45/CloneUp.git"
    cases = [
        (
            "https://github.com/seongbin45/CloneUp/tree/main",
            "https://github.com/seongbin45/CloneUp.git",
            True,
        ),
        (
            "https://github.com/seongbin45/CloneUp.git",
            "https://github.com/seongbin45/CloneUp.git",
            False,
        ),
        (
            ssh_sample,
            "https://github.com/seongbin45/CloneUp.git",
            False,
        ),
    ]
    for raw, expect, expect_warn in cases:
        try:
            n = normalize_github_clone_url(raw)
            if n.clone_url != expect:
                fail(f"normalize {raw[:40]}", f"got {n.clone_url}")
            elif expect_warn and not n.warnings:
                fail(f"normalize warn {raw[:40]}", "warning 없음")
            else:
                ok(f"normalize {raw[:48]}", n.clone_url)
        except Exception as e:
            fail(f"normalize {raw[:40]}", str(e))

    try:
        normalize_github_clone_url("https://gitlab.com/x/y")
        fail("non-github 거절", "예외 없음")
    except UrlError:
        ok("non-github 거절")
    except Exception as e:
        fail("non-github 거절", str(e))

    # ----- safety -----
    section("안전 검사 (S1/S3/G2 성격)")
    empty = Path(tempfile.mkdtemp(prefix="cu-v-empty-"))
    r = run_safety_checks(empty)
    if r.ok is False and any("빈 폴더" in e for e in r.errors):
        ok("S1 빈 폴더 차단")
    else:
        fail("S1 빈 폴더 차단", str(r.errors))

    sec = Path(tempfile.mkdtemp(prefix="cu-v-secret-"))
    (sec / "a.txt").write_text("x\n", encoding="utf-8")
    (sec / ".env").write_text("SECRET=1\n", encoding="utf-8")
    r2 = run_safety_checks(sec)
    if r2.ok is False and any(".env" in e for e in r2.errors):
        ok("S3 .env 차단")
    else:
        fail("S3 .env 차단", str(r2.errors))

    r3 = run_safety_checks(sec, allow_secrets=True)
    if r3.ok:
        ok("S3 allow_secrets 통과")
    else:
        fail("S3 allow_secrets 통과", str(r3.errors))

    # G2: folder with origin
    g2 = Path(tempfile.mkdtemp(prefix="cu-v-origin-"))
    (g2 / "f.txt").write_text("x\n", encoding="utf-8")
    run_git(["init", "-b", "main"], cwd=str(g2), check=True)
    run_git(
        ["remote", "add", "origin", "https://github.com/example/repo.git"],
        cwd=str(g2),
        check=True,
    )
    from app.git.publish import publish_local_to_existing_remote

    try:
        publish_local_to_existing_remote(
            g2,
            token="fake-token-not-used",
            user={"id": 1, "login": "x", "name": "x"},
            clone_url="https://github.com/x/y.git",
            html_url="https://github.com/x/y",
            full_name="x/y",
        )
        fail("G2 origin 이미 있음", "예외 없음")
    except PublishError as e:
        if "origin" in str(e).lower():
            ok("G2 origin 이미 있음", str(e)[:60])
        else:
            fail("G2 origin 이미 있음", str(e))
    except Exception as e:
        # may fail earlier on safety if secrets — should not
        fail("G2 origin 이미 있음", f"{type(e).__name__}: {e}")

    # ----- mask -----
    section("토큰 마스킹")
    sample = "token gho_abcdefghijklmnopqrstuvwxyz012345 and more"
    masked = mask_secrets_in_text(sample)
    if "gho_abcdefghijklmnopqrstuvwxyz012345" not in masked and "gho_" in masked:
        ok("mask_secrets_in_text")
    else:
        fail("mask_secrets_in_text", masked)

    # ----- clone public -----
    section("Clone (public, 토큰 없음)")
    parent = Path(tempfile.mkdtemp(prefix="cu-v-clone-"))
    try:
        cr = clone_repository(
            "https://github.com/seongbin45/CloneUp/tree/main",
            parent,
            directory_name="cu-cross-clone",
            token=None,
        )
        if not (cr.target_dir / ".git").is_dir():
            fail("public clone", ".git 없음")
        else:
            rv = run_git(["remote", "-v"], cwd=str(cr.target_dir), check=True)
            remote_out = rv.stdout or ""
            if "x-access-token" in remote_out.lower() or "gho_" in remote_out:
                fail("clone remote 깨끗", remote_out[:120])
            elif "github.com/seongbin45/CloneUp.git" in remote_out:
                ok("public clone + clean remote", str(cr.target_dir))
            else:
                fail("clone remote URL", remote_out[:120])
            clone_path = cr.target_dir
    except Exception as e:
        fail("public clone", str(e))
        clone_path = None

    # existing path
    if clone_path is not None:
        try:
            clone_repository(
                "https://github.com/seongbin45/CloneUp",
                parent,
                directory_name="cu-cross-clone",
                token=None,
            )
            fail("clone 경로 충돌", "예외 없음")
        except CloneError as e:
            if "이미 존재" in str(e):
                ok("clone 경로 충돌 차단")
            else:
                fail("clone 경로 충돌", str(e))

    # ----- sync status / pull -----
    section("Sync (public clone 기준)")
    if clone_path is None:
        skip("sync status", "clone 실패로 스킵")
    else:
        try:
            st = get_repo_status(clone_path)
            if st.has_origin and st.branch:
                ok("sync status", st.summary)
            else:
                fail("sync status", st.summary)
        except Exception as e:
            fail("sync status", str(e))

        try:
            # pull without token on public repo
            msg = pull_repo(clone_path, token=None)
            ok("sync pull (public)", msg[:80].replace("\n", " "))
        except Exception as e:
            fail("sync pull (public)", str(e))

        try:
            get_repo_status(Path(tempfile.mkdtemp(prefix="cu-v-nogit-")))
            fail("sync .git 없음", "예외 없음")
        except SyncError:
            ok("sync .git 없음 차단")
        except Exception as e:
            fail("sync .git 없음", str(e))

    # ----- auth-dependent -----
    section("인증 필요 (API / private / publish)")
    if not auth_ok:
        skip("GET /user", "토큰 없음")
        skip("create public repo", "토큰 없음")
        skip("create private repo", "토큰 없음")
        skip("publish E2E", "토큰 없음")
        skip("credential helper fill", "토큰 없음")
    else:
        try:
            user = get_authenticated_user(token)
            if user.get("login"):
                ok("GET /user", user.get("login"))
            else:
                fail("GET /user", str(user)[:80])
        except Exception as e:
            fail("GET /user", str(e))
            user = {"id": 0, "login": "unknown", "name": "unknown"}

        # credential store format
        try:
            cpath = write_credential_file(token)
            text = Path(cpath).read_text(encoding="utf-8")
            delete_credential_file(cpath)
            if text.startswith("https://x-access-token:") and text.rstrip().endswith(
                "@github.com/"
            ):
                ok("credential file 형식", "trailing slash OK")
            else:
                fail("credential file 형식", repr(text[:40]))
        except Exception as e:
            fail("credential file 형식", str(e))

        # create public empty
        import time

        stamp = time.strftime("%Y%m%d-%H%M%S")
        pub_name = f"cloneup-verify-pub-{stamp}"
        priv_name = f"cloneup-verify-priv-{stamp}"
        try:
            repo = create_repo(
                token, pub_name, private=False, description="verify", auto_init=False
            )
            if repo.get("private") is False and repo.get("clone_url"):
                ok("API public create", repo.get("full_name"))
            else:
                fail("API public create", str(repo)[:100])
        except Exception as e:
            fail("API public create", str(e))
            repo = None

        if has_scope("repo") or (scope and "repo" in str(scope).split()):
            try:
                prepo = create_repo(
                    token,
                    priv_name,
                    private=True,
                    description="verify private",
                    auto_init=False,
                )
                if prepo.get("private") is True:
                    ok("API private create", prepo.get("full_name"))
                else:
                    fail("API private create", f"private={prepo.get('private')}")
            except Exception as e:
                fail("API private create", str(e))
        else:
            skip("API private create", f"scope={scope!r}")

        # publish E2E small folder
        pub_dir = Path(tempfile.mkdtemp(prefix="cu-v-pub-"))
        (pub_dir / "hello.txt").write_text("cross-verify\n", encoding="utf-8")
        pub_repo_name = f"cloneup-verify-push-{stamp}"
        try:
            result = publish_folder_to_new_repo(
                pub_dir,
                token=token,
                user=user,
                create_repo_fn=create_repo,
                repo_name=pub_repo_name,
                description="cross verify publish",
                commit_message="verify",
                private=False,
            )
            cfg = (pub_dir / ".git" / "config").read_text(encoding="utf-8")
            if token in cfg or "x-access-token" in cfg.lower():
                fail("publish config 깨끗", "토큰 잔존")
            elif result.config_clean and result.html_url:
                ok("publish E2E", result.full_name)
            else:
                fail("publish E2E", str(result))
            # sync status on published folder
            st2 = get_repo_status(pub_dir)
            if st2.has_origin:
                ok("publish 후 sync status", st2.summary)
            else:
                fail("publish 후 sync status", st2.summary)
        except Exception as e:
            fail("publish E2E", str(e))

        # auto_init reject
        try:
            create_repo(token, "x", auto_init=True)
            fail("auto_init 거절", "예외 없음")
        except ValueError:
            ok("auto_init 거절")
        except Exception as e:
            fail("auto_init 거절", str(e))

    # ----- UI load -----
    section("UI 로드")
    try:
        from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton

        app = QApplication.instance() or QApplication([])
        from app.ui.main_window import load_main_window

        w = load_main_window()
        need = [
            ("btnPublish", QPushButton),
            ("btnClone", QPushButton),
            ("btnSyncPull", QPushButton),
            ("btnSyncPush", QPushButton),
            ("btnSyncAbort", QPushButton),
            ("editCloneUrl", QLineEdit),
            ("editSyncFolder", QLineEdit),
            ("comboSyncRecent", QComboBox),
            ("btnSyncRefresh", QPushButton),
            ("btnSyncBrowse", QPushButton),
        ]
        missing = []
        for name, cls in need:
            if w.findChild(cls, name) is None:
                missing.append(name)
        if missing:
            fail("UI 위젯", str(missing))
        else:
            ok("UI 위젯 (Publish/Clone/Sync)")
        w.close()
    except Exception as e:
        fail("UI 로드", str(e))

    # cleanup note
    section("정리 안내")
    RESULTS.append(
        "원격에 cloneup-verify-* 저장소가 생겼을 수 있습니다. "
        "GitHub 웹에서 수동 삭제하세요 (delete_repo scope 없음)."
    )

    _print_report()
    if FAIL:
        return 1
    if not auth_ok:
        return 2
    return 0


def _print_report() -> None:
    print("=" * 60)
    print("CloneUp cross-verify report")
    print("=" * 60)
    for line in RESULTS:
        print(line)
    print()
    print(f"요약: PASS={PASS}  FAIL={FAIL}  SKIP={SKIP}")
    print("=" * 60)


if __name__ == "__main__":
    raise SystemExit(main())
