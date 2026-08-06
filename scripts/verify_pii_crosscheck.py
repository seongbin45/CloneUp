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
    check(
        "skips .* dirs (broader than ref .git-only)",
        "010-3333-4444" not in samples,
        "dot-dir content intentionally skipped",
    )

    secrets = s.find_secret_candidates(td)
    check("filename secret .env", ".env" in secrets, str(secrets))

    rep_block = s.run_safety_checks(td, allow_secrets=False, write_gitignore=False)
    check("blocks without allow_secrets on .env", not rep_block.ok)
    check("pii_hits on report", len(rep_block.pii_hits) >= 1, str(len(rep_block.pii_hits)))

    rep_allow = s.run_safety_checks(td, allow_secrets=True, write_gitignore=False)
    check("allows with allow_secrets", rep_allow.ok)
    check("still warns on pii", any("개인정보" in w for w in rep_allow.warnings))

    # 4) UI G3 wiring
    from app.ui.main_window import MainController
    import inspect

    src = inspect.getsource(MainController._confirm_upload_g3)
    check("G3 calls scan_pii_in_contents", "scan_pii_in_contents" in src)
    check("G3 calls find_secret_candidates", "find_secret_candidates" in src)
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
        "scan_pii" not in sync_src,
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
