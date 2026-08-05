#!/usr/bin/env python3
"""
CloneUp — Stage 1 spike (no UI)

Device Flow → OS keyring (token + scope) → GET /user
401 on stored token → delete keyring → auto Device Flow (no --force required)

Usage:
  .\\.venv\\Scripts\\python.exe spike_device_flow.py
  .\\.venv\\Scripts\\python.exe spike_device_flow.py --force
  .\\.venv\\Scripts\\python.exe spike_device_flow.py --logout
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth.session import AuthError, ensure_valid_token
from app.auth.token_store import delete_token, load_scope
from app.config import get_github_client_id, get_github_scopes
from app.util.log_mask import mask_token


def main() -> int:
    parser = argparse.ArgumentParser(description="CloneUp Device Flow spike")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Discard keyring token and run Device Flow again",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Delete token+scope from keyring only",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically",
    )
    args = parser.parse_args()

    if args.logout:
        delete_token()
        print("keyring 토큰·scope 삭제 완료.")
        print(
            "완전 해제는 https://github.com/settings/applications 에서 앱 권한을 취소하세요."
        )
        return 0

    client_id = get_github_client_id()
    print(
        f"Client ID source: "
        f"len={len(client_id)} "
        f"(env override or built-in default; not a secret)"
    )
    print(f"Requested scopes for new login: {get_github_scopes()!r}")

    try:
        token, user = ensure_valid_token(
            force_login=args.force,
            open_browser=not args.no_browser,
        )
    except AuthError as e:
        print(f"ERROR: 인증 — {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: 네트워크 — {e}", file=sys.stderr)
        return 1

    login = user.get("login", "?")
    name = user.get("name") or "(이름 없음)"
    print()
    print("=== Spike 1 성공 ===")
    print(f"  GitHub login  : {login}")
    print(f"  Name          : {name}")
    print(f"  Token (masked): {mask_token(token)}")
    print(f"  Scope (stored): {load_scope()!r}")
    print("  Storage       : OS keyring (service=CloneUp)")
    print()
    print("다음: 2단계 API 스파이크 (POST /user/repos, auto_init 없음)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
