#!/usr/bin/env python3
"""Cross-verify CloneUp PII/safety vs Command-to-commit-changes-from-Git."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.git import safety as s  # noqa: E402

# Reference README §1-4
REF_PHONE = r"01[0-9]-?[0-9]{3,4}-?[0-9]{4}"
REF_EMAIL = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

ANON_BIN = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",
    ".zip",
    ".rar",
    ".7z",
    ".pdf",
    ".exe",
    ".dll",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
}
ANON_SKIP = {".git", "__pycache__", "node_modules"}


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {name}" + (f" — {detail}" if detail else ""))

    # 1) Regex identity
    check(
        "phone regex == README",
        s._PHONE_RE.pattern == REF_PHONE,
        repr(s._PHONE_RE.pattern),
    )
    check(
        "email regex == README",
        s._EMAIL_RE.pattern == REF_EMAIL,
        repr(s._EMAIL_RE.pattern),
    )

    phone_cases = [
        ("010-1234-5678", True),
        ("01012345678", True),
        ("011-123-4567", True),
        ("02-123-4567", False),
    ]
    for text, expect in phone_cases:
        ref = bool(re.search(REF_PHONE, text))
        ours = bool(s._PHONE_RE.search(text))
        check(
            f"phone sample {text!r}",
            ref == ours == expect,
            f"ref={ref} ours={ours} expect={expect}",
        )

    # 2) Binary extensions cover anonymize set
    check(
        "binary set ⊇ anonymize.py",
        ANON_BIN <= s._BINARY_EXTENSIONS,
        f"missing={ANON_BIN - s._BINARY_EXTENSIONS}",
    )
    check(
        "skip dirs ⊇ anonymize.py",
        ANON_SKIP <= s._SKIP_DIRS,
        f"missing={ANON_SKIP - s._SKIP_DIRS}",
    )

    # 3) Functional scan
    td = Path(tempfile.mkdtemp(prefix="cloneup_pii_"))
    (td / ".env").write_text("K=1\n", encoding="utf-8")
    (td / "note.txt").write_text(
        "call 010-9999-8888 or real@univ.ac.kr and ignore@example.com\n",
        encoding="utf-8",
    )
    (td / "leaked.txt").write_text(
        "token = ghp_abcdefghijklmnopqrstuvwxyz012345\n"
        "aws = AKIAIOSFODNN7EXAMPLE\n",
        encoding="utf-8",
    )
    (td / "img.png").write_bytes(b"\x89PNG fake 010-1111-2222")
    hidden = td / ".cache"
    hidden.mkdir()
    (hidden / "x.txt").write_text("010-3333-4444\n", encoding="utf-8")

    hits = s.scan_pii_in_contents(td)
    samples = {h.sample for h in hits}
    check("detects phone in note.txt", "010-9999-8888" in samples, str(samples))
    check("detects school email", "real@univ.ac.kr" in samples, str(samples))
    check(
        "filters example.com email",
        "ignore@example.com" not in samples,
        str(samples),
    )
    check(
        "does not scan png bytes as text phone",
        "010-1111-2222" not in samples,
        str(samples),
    )
    # H1 fix: do not skip all ".*" dirs — .github etc. must be scanned.
    # Without git, .cache is still publishable → phone may appear (expected).
    paths_pub, _ = s.list_publishable_relpaths(td)
    check(
        "publishable includes non-git files",
        any("note.txt" in p for p in paths_pub),
        str(paths_pub[:10]),
    )
    check(
        "does not skip .github-style paths by default",
        not s._should_skip_dir(".github"),
        "only .git + vendor skip dirs",
    )

    secrets = s.find_secret_candidates(td)
    check("filename secret .env", ".env" in secrets, str(secrets))

    csec = s.scan_secret_in_contents(td)
    csec_kinds = {h.kind for h in csec}
    check(
        "content secret github_token",
        "github_token" in csec_kinds,
        str(csec_kinds),
    )
    check(
        "content secret aws_access_key",
        "aws_access_key" in csec_kinds,
        str(csec_kinds),
    )
    check(
        "content secret samples masked",
        all("ghp_abcdefgh" not in h.sample for h in csec),
        str([h.sample for h in csec]),
    )

    rep_block = s.run_safety_checks(td, allow_secrets=False, write_gitignore=False)
    check("blocks without allow_secrets on .env", not rep_block.ok)
    check(
        "blocks content secrets without allow",
        any("내용" in e or "비밀" in e for e in rep_block.errors),
        str(rep_block.errors),
    )
    check("pii_hits on report", len(rep_block.pii_hits) >= 1, str(len(rep_block.pii_hits)))
    check(
        "content_secret_hits on report",
        len(rep_block.content_secret_hits) >= 1,
        str(len(rep_block.content_secret_hits)),
    )

    # Filename-only allow: content hard secrets (ghp_/AKIA) still block
    rep_allow = s.run_safety_checks(td, allow_secrets=True, write_gitignore=False)
    check(
        "allow_secrets still blocks hard content secrets",
        not rep_allow.ok and len(rep_allow.content_secret_hits) >= 1,
        str(rep_allow.errors)[:120],
    )
    # Filename-only tree: allow_secrets opens .env-style names
    td2 = Path(tempfile.mkdtemp(prefix="cloneup_pii_fn_"))
    (td2 / ".env").write_text("K=1\n", encoding="utf-8")
    (td2 / "note.txt").write_text("hello only\n", encoding="utf-8")
    rep_fn = s.run_safety_checks(td2, allow_secrets=True, write_gitignore=False)
    check("allows filename secrets with allow_secrets", rep_fn.ok)
    rep_pii = s.run_safety_checks(td, allow_secrets=True, write_gitignore=False)
    check("still warns on pii", any("개인정보" in w for w in rep_pii.warnings))

    # 4) UI G3 wiring
    from app.ui.main_window import MainController
    import inspect

    src = inspect.getsource(MainController._confirm_upload_g3)
    check("G3 calls scan_pii_in_contents", "scan_pii_in_contents" in src)
    check("G3 calls find_secret_candidates", "find_secret_candidates" in src)
    check(
        "G3 calls scan_secret_in_contents",
        "scan_secret_in_contents" in src,
    )
    # Copy shortened for beginners — match current G3 wording, not old phrases
    check(
        "G3 shows content PII copy",
        "개인정보 후보" in src or "개인정보" in src,
    )
    check(
        "G3 shows commit email",
        "커밋에 남을 주소" in src or "preview_commit_email" in src,
    )

    # 5) Intentional non-goals vs reference
    check(
        "no anonymize replace API (intentional)",
        not hasattr(s, "apply_replacements"),
        "substitution is out of CloneUp scope",
    )
    check(
        "no student-id regex (ref also had none)",
        "학번" not in Path(s.__file__).read_text(encoding="utf-8"),
    )

    # sync_ops: secrets only at worker (G3 covers PII on UI push)
    sync_src = (ROOT / "app" / "git" / "sync_ops.py").read_text(encoding="utf-8")
    check(
        "sync_ops uses filename secrets",
        "find_secret_candidates" in sync_src,
    )
    check(
        "sync_ops does not re-scan PII (UI G3 does)",
        "scan_pii=False" in sync_src or "scan_pii_in_contents" not in sync_src,
        "OK if main_window G3 runs before push",
    )

    failed = [n for n, ok, _ in results if not ok]
    print()
    print(f"TOTAL {len(results)}  PASS {len(results) - len(failed)}  FAIL {len(failed)}")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("CROSS_VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
