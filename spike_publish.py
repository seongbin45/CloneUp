#!/usr/bin/env python3
"""
CloneUp — Stage 3 spike (no UI)

Publish local folder → new empty public GitHub repo:
  safety → gitignore → init -b main → add → commit (-c identity if needed)
  → remote clean URL → push via temp credential.helper store file
  → assert .git/config has no token

Usage:
  .\\.venv\\Scripts\\python.exe spike_publish.py --folder PATH
  .\\.venv\\Scripts\\python.exe spike_publish.py --folder PATH --name my-repo
  .\\.venv\\Scripts\\python.exe spike_publish.py --folder PATH --allow-secrets

Uses existing empty remote if --clone-url / --html-url / --full-name given
(from stage 2 handoff); otherwise creates a new public repo (no auto_init).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth.session import AuthError, ensure_valid_token
from app.auth.token_store import load_scope
from app.git.publish import PublishError, publish_folder_to_new_repo, publish_local_to_existing_remote
from app.git.runner import GitError, require_git
from app.github.api_client import create_repo
from app.util.log_mask import mask_token

_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def main() -> int:
    parser = argparse.ArgumentParser(description="CloneUp publish spike")
    parser.add_argument(
        "--folder",
        help="Local folder to publish (default: create a temp demo folder)",
    )
    parser.add_argument(
        "--name",
        help="New GitHub repo name (default: cloneup-publish-YYYYMMDD-HHMM)",
    )
    parser.add_argument(
        "--message",
        default="Initial commit",
        help="Commit message",
    )
    parser.add_argument(
        "--allow-secrets",
        action="store_true",
        help="Allow files that look like secrets (.env, keys, …)",
    )
    parser.add_argument(
        "--clone-url",
        help="Stage-2 handoff: use existing empty repo clone_url",
    )
    parser.add_argument(
        "--html-url",
        help="Stage-2 handoff: html_url",
    )
    parser.add_argument(
        "--full-name",
        help="Stage-2 handoff: owner/repo",
    )
    parser.add_argument(
        "--keep-demo",
        action="store_true",
        help="If using temp demo folder, do not delete it after success",
    )
    args = parser.parse_args()

    try:
        exe, ver = require_git()
        print(f"Git: {exe} version {ver[0]}.{ver[1]}.{ver[2]}")
    except GitError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        token, user = ensure_valid_token()
    except AuthError as e:
        print(f"ERROR: 인증 — {e}", file=sys.stderr)
        return 1

    print(f"Token (masked): {mask_token(token)}")
    print(f"User: {user.get('login')} id={user.get('id')}")
    print(f"Stored scope: {load_scope()!r}")

    demo_dir: Path | None = None
    if args.folder:
        folder = Path(args.folder).expanduser().resolve()
    else:
        demo_dir = Path(
            tempfile.mkdtemp(prefix="cloneup-publish-demo-")
        )
        (demo_dir / "README.md").write_text(
            "# CloneUp publish spike\n\nThis folder was published by spike_publish.py.\n",
            encoding="utf-8",
            newline="\n",
        )
        (demo_dir / "hello.txt").write_text("hello from CloneUp\n", encoding="utf-8")
        folder = demo_dir
        print(f"데모 폴더 생성: {folder}")

    if not folder.is_dir():
        print(f"ERROR: 폴더 없음: {folder}", file=sys.stderr)
        return 2

    name = args.name
    if not name and not args.clone_url:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        name = f"cloneup-publish-{stamp}"

    if name and not _REPO_NAME_RE.match(name):
        print("ERROR: 저장소 이름은 영문/숫자/._- 만 가능합니다.", file=sys.stderr)
        return 2

    try:
        if args.clone_url:
            if not args.html_url or not args.full_name:
                print(
                    "ERROR: --clone-url 사용 시 --html-url 과 --full-name 도 필요합니다.",
                    file=sys.stderr,
                )
                return 2
            print(f"기존 빈 원격 사용: {args.full_name}")
            result = publish_local_to_existing_remote(
                folder,
                token=token,
                user=user,
                clone_url=args.clone_url,
                html_url=args.html_url,
                full_name=args.full_name,
                commit_message=args.message,
                allow_secrets=args.allow_secrets,
            )
        else:
            assert name is not None
            print(f"새 public 저장소 생성 후 업로드: {name}")
            result = publish_folder_to_new_repo(
                folder,
                token=token,
                user=user,
                create_repo_fn=create_repo,
                repo_name=name,
                description="CloneUp publish spike — safe to delete on github.com",
                commit_message=args.message,
                allow_secrets=args.allow_secrets,
            )
    except PublishError as e:
        print(f"ERROR: publish — {e}", file=sys.stderr)
        return 1
    except GitError as e:
        print(f"ERROR: git — {e}", file=sys.stderr)
        return 1

    print()
    print("=== Spike 3 성공 ===")
    print(f"  folder     : {result.folder}")
    print(f"  full_name  : {result.full_name}")
    print(f"  html_url   : {result.html_url}")
    print(f"  clone_url  : {result.clone_url}")
    print(f"  message    : {result.commit_message}")
    print(f"  config_clean (no token in .git/config): {result.config_clean}")
    if result.safety.wrote_gitignore:
        print("  gitignore  : 기본 템플릿 생성됨")
    if result.safety.warnings:
        for w in result.safety.warnings:
            print(f"  warning    : {w}")
    print()
    print("브라우저에서 파일 2개(README/hello 또는 사용자 파일)가 보이는지 확인하세요.")
    print("정리: public_repo 로는 DELETE 불가 → GitHub 웹에서 수동 삭제.")

    if demo_dir and not args.keep_demo:
        # keep .git for inspection? user may want to inspect config — keep demo if --keep-demo
        pass  # leave temp folder; OS will clean eventually. Prefer keep for verification.
        print(f"데모 폴더 유지(검사 가능): {demo_dir}")
        print("  확인: type .git\\config  에 토큰 없는지 보세요.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
