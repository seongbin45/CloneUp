#!/usr/bin/env python3
"""
CloneUp — Stage 2 spike (no UI)

ensure_valid_token → POST /user/repos (public, no auto_init)

Prints for stage 3 handoff: full_name, html_url, clone_url

Usage:
  .\\.venv\\Scripts\\python.exe spike_create_repo.py
  .\\.venv\\Scripts\\python.exe spike_create_repo.py --name my-test-repo

Note: DELETE needs delete_repo scope (not in public_repo).
Cleanup is manual on github.com — names use cloneup-spike-YYYYMMDD-HHMM.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth.session import AuthError, ensure_valid_token
from app.auth.token_store import load_scope
from app.github.api_client import GitHubAPIError, create_repo
from app.util.log_mask import mask_token

_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _friendly_create_error(e: GitHubAPIError) -> str:
    if e.status == 401:
        return (
            "인증 실패(401). 세션 계층이 재로그인을 시도했어야 합니다. "
            "spike_device_flow.py --force 후 다시 시도하세요."
        )
    if e.status == 403:
        return (
            "권한 부족(403). public_repo 스코프인지 확인하세요. "
            f"stored scope={load_scope()!r}. 상세: {e.message}"
        )
    if e.status == 422:
        return (
            "요청 거부(422) — 보통 같은 이름 저장소가 이미 있습니다. "
            f"--name 으로 다른 이름을 쓰세요. 상세: {e.message}"
        )
    return f"HTTP {e.status}: {e.message}"


def main() -> int:
    parser = argparse.ArgumentParser(description="CloneUp create-repo API spike")
    parser.add_argument(
        "--name",
        help="Repository name (default: cloneup-spike-YYYYMMDD-HHMM UTC)",
    )
    parser.add_argument(
        "--description",
        default="CloneUp spike 2 — safe to delete manually on github.com",
        help="Repo description",
    )
    args = parser.parse_args()

    try:
        token, user = ensure_valid_token()
    except AuthError as e:
        print(f"ERROR: 인증 — {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: 네트워크 — {e}", file=sys.stderr)
        return 1

    login = user.get("login", "?")
    print(f"Token (masked): {mask_token(token)}")
    print(f"Authenticated as: {login}")
    print(f"Stored scope: {load_scope()!r}")

    name = args.name
    if not name:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        name = f"cloneup-spike-{stamp}"

    if not _REPO_NAME_RE.match(name):
        print(
            "ERROR: 저장소 이름은 영문/숫자/._- 만 사용할 수 있습니다.",
            file=sys.stderr,
        )
        return 2

    print(f"Creating public empty repo (no auto_init): {login}/{name}")
    try:
        repo = create_repo(
            token,
            name,
            private=False,
            description=args.description,
            auto_init=False,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except GitHubAPIError as e:
        print(f"ERROR: POST /user/repos — {_friendly_create_error(e)}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: 네트워크 — {e}", file=sys.stderr)
        return 1

    full_name = repo.get("full_name", f"{login}/{name}")
    html_url = repo.get("html_url", "")
    clone_url = repo.get("clone_url", "")
    private = repo.get("private")

    print()
    print("=== Spike 2 성공 (3단계 핸드오프) ===")
    print(f"  full_name : {full_name}")
    print(f"  html_url  : {html_url}")
    print(f"  clone_url : {clone_url}")
    print(f"  private   : {private}  (expect False)")
    print()
    print("정리: public_repo로는 DELETE 불가 → GitHub 웹에서 수동 삭제하세요.")
    print("다음: 3단계 publish (init -b main, clean remote, credential-helper push)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
