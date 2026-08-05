"""Pre-publish safety checks for beginner-friendly defaults.

Secret *filenames* + file-*content* PII patterns (cross-check:
Command-to-commit-changes-from-Git README / anonymize.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Minimal template written when the folder has no .gitignore
DEFAULT_GITIGNORE = """\
# CloneUp default — review before publishing
.env
.env.*
!.env.example
*.pem
*.key
id_rsa
id_rsa.*
id_ed25519
id_ed25519.*
__pycache__/
*.py[cod]
.venv/
venv/
node_modules/
.DS_Store
Thumbs.db
"""

# Paths (relative posix) that look like secrets if staged
_SECRET_NAME_RE = re.compile(
    r"""(?ix)
    (
      ^\.env$ |
      ^\.env\. |
      \.pem$ |
      \.key$ |
      (^|/)id_rsa$ |
      (^|/)id_ed25519$ |
      secret |
      credentials |
      \.p12$ |
      \.pfx$
    )
    """
)

# --- Content PII (from Command-to-commit-changes-from-Git README §1-4) ---
# phone: 01[0-9]-?[0-9]{3,4}-?[0-9]{4}
# email: standard address shape
_PHONE_RE = re.compile(r"01[0-9]-?[0-9]{3,4}-?[0-9]{4}")
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Same spirit as anonymize.py BINARY_EXTENSIONS + SKIP_DIRS
_BINARY_EXTENSIONS = {
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
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".svg",  # often large; skip content scan
}
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    "dist",
    "build",
    ".idea",
    ".vs",
}

# Cap work for large trees
_MAX_FILE_BYTES = 512 * 1024
_MAX_FILES_SCANNED = 2000
_MAX_PII_HITS = 40

# Soft-ignore obvious non-personal emails (examples / tooling)
_EMAIL_IGNORE_SUBSTR = (
    "example.com",
    "example.org",
    "test.com",
    "localhost",
    "noreply",
    "no-reply",
    "users.noreply.github.com",
    "sentry.io",
    "w3.org",
    "schema.org",
    "github.com",
    "githubusercontent.com",
)


@dataclass(frozen=True)
class PiiHit:
    path: str  # relative posix
    kind: str  # "phone" | "email"
    sample: str  # matched text (masked for display if needed)


@dataclass
class SafetyReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    secret_candidates: list[str] = field(default_factory=list)
    pii_hits: list[PiiHit] = field(default_factory=list)
    wrote_gitignore: bool = False


def is_effectively_empty(folder: Path) -> bool:
    """True if no real files to publish (ignoring .git and our soon-to-be gitignore)."""
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(folder).parts
        if rel_parts and rel_parts[0] == ".git":
            continue
        return False
    return True


def find_secret_candidates(folder: Path) -> list[str]:
    hits: list[str] = []
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(folder).as_posix()
        if rel.startswith(".git/"):
            continue
        name = p.name
        if _SECRET_NAME_RE.search(name) or _SECRET_NAME_RE.search(rel):
            hits.append(rel)
    return sorted(hits)


def format_secret_list(secrets: list[str], *, limit: int = 20) -> str:
    """Bullet list for UI dialogs (G3)."""
    if not secrets:
        return ""
    head = secrets[:limit]
    lines = "\n".join(f"  · {s}" for s in head)
    if len(secrets) > limit:
        lines += f"\n  · … 외 {len(secrets) - limit}개"
    return lines


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".")


def _email_ignored(addr: str) -> bool:
    low = addr.lower()
    return any(s in low for s in _EMAIL_IGNORE_SUBSTR)


def scan_pii_in_contents(folder: Path) -> list[PiiHit]:
    """
    Scan text file bodies for phone/email (reference project grep patterns).

    Does not replace strings (that is anonymize.py's job). Returns hits for UI.
    """
    root = folder.resolve()
    hits: list[PiiHit] = []
    seen: set[tuple[str, str, str]] = set()
    files_seen = 0

    for dirpath, dirnames, filenames in os_walk_skip(root):
        # prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for name in filenames:
            if files_seen >= _MAX_FILES_SCANNED or len(hits) >= _MAX_PII_HITS:
                return hits
            ext = Path(name).suffix.lower()
            if ext in _BINARY_EXTENSIONS:
                continue
            path = Path(dirpath) / name
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files_seen += 1
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            rel = path.relative_to(root).as_posix()
            for m in _PHONE_RE.finditer(text):
                sample = m.group(0)
                key = (rel, "phone", sample)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(PiiHit(path=rel, kind="phone", sample=sample))
                if len(hits) >= _MAX_PII_HITS:
                    return hits
            for m in _EMAIL_RE.finditer(text):
                sample = m.group(0)
                if _email_ignored(sample):
                    continue
                key = (rel, "email", sample)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(PiiHit(path=rel, kind="email", sample=sample))
                if len(hits) >= _MAX_PII_HITS:
                    return hits
    return hits


def os_walk_skip(root: Path):
    """os.walk from root (pathlib)."""
    import os

    return os.walk(root)


def format_pii_list(hits: list[PiiHit], *, limit: int = 15) -> str:
    if not hits:
        return ""
    kind_ko = {"phone": "전화", "email": "이메일"}
    lines: list[str] = []
    for h in hits[:limit]:
        label = kind_ko.get(h.kind, h.kind)
        lines.append(f"  · [{label}] {h.sample}  ← {h.path}")
    if len(hits) > limit:
        lines.append(f"  · … 외 {len(hits) - limit}건")
    return "\n".join(lines)


def ensure_gitignore(folder: Path, *, write_if_missing: bool = True) -> bool:
    """Return True if a new .gitignore was written."""
    gi = folder / ".gitignore"
    if gi.exists():
        return False
    if write_if_missing:
        gi.write_text(DEFAULT_GITIGNORE, encoding="utf-8", newline="\n")
        return True
    return False


def run_safety_checks(
    folder: Path,
    *,
    allow_secrets: bool = False,
    write_gitignore: bool = True,
    scan_pii: bool = True,
) -> SafetyReport:
    report = SafetyReport(ok=True)
    if not folder.is_dir():
        report.ok = False
        report.errors.append(f"폴더가 없습니다: {folder}")
        return report

    if is_effectively_empty(folder):
        report.ok = False
        report.errors.append(
            "빈 폴더입니다. 커밋할 파일이 최소 1개 있어야 합니다."
        )
        return report

    if write_gitignore:
        report.wrote_gitignore = ensure_gitignore(folder, write_if_missing=True)
        if report.wrote_gitignore:
            report.warnings.append("기본 .gitignore 를 새로 만들었습니다. 내용을 확인하세요.")

    secrets = find_secret_candidates(folder)
    report.secret_candidates = secrets
    if secrets and not allow_secrets:
        report.ok = False
        report.errors.append(
            "비밀 파일로 보이는 항목이 있습니다. 제거하거나 "
            f"--allow-secrets 로 명시 확인하세요: {', '.join(secrets)}"
        )
    elif secrets:
        report.warnings.append(
            f"--allow-secrets: 다음 파일이 포함될 수 있습니다: {', '.join(secrets)}"
        )

    if scan_pii:
        pii = scan_pii_in_contents(folder)
        report.pii_hits = pii
        if pii:
            report.warnings.append(
                f"파일 내용에서 개인정보로 보이는 패턴 {len(pii)}건 "
                f"(전화/이메일). 업로드 전 확인하세요."
            )

    return report
