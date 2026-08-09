"""Pre-publish safety checks for beginner-friendly defaults.

Secret *filenames* + file-*content* PII / known secret patterns
(cross-check: Command-to-commit-changes-from-Git README / anonymize.py + M4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.util.log_mask import mask_secrets_in_text

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
_MAX_CONTENT_SECRET_HITS = 40

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

# M4 — high-confidence secret *content* (not just filename)
_CONTENT_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "github_token",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("aws_access_key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    (
        "private_key",
        # Requires a matching END line, not just the header — a README
        # explaining PEM format (or showing the header as an example) would
        # otherwise hard-block forever, since this kind has no allow_secrets
        # bypass. A real leaked key always has both BEGIN and END.
        re.compile(
            r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    ("slack_token", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("stripe_key", re.compile(r"\b(sk_live_[A-Za-z0-9]{20,}|sk_test_[A-Za-z0-9]{20,})\b")),
    ("google_api_key", re.compile(r"\b(AIza[0-9A-Za-z_-]{30,})\b")),
]

_CONTENT_SECRET_KIND_KO = {
    "github_token": "GitHub 키",
    "aws_access_key": "AWS 키",
    "private_key": "개인 키 파일 내용",
    "slack_token": "Slack 토큰",
    "stripe_key": "Stripe 키",
    "google_api_key": "Google API 키",
}


@dataclass(frozen=True)
class PiiHit:
    path: str  # relative posix
    kind: str  # "phone" | "email"
    sample: str  # matched text (masked for display if needed)


@dataclass(frozen=True)
class ContentSecretHit:
    path: str
    kind: str  # see _CONTENT_SECRET_PATTERNS
    sample: str  # already masked for UI/logs


@dataclass
class SafetyReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    secret_candidates: list[str] = field(default_factory=list)
    pii_hits: list[PiiHit] = field(default_factory=list)
    content_secret_hits: list[ContentSecretHit] = field(default_factory=list)
    wrote_gitignore: bool = False
    # How many publishable paths we considered / whether scan was truncated
    paths_considered: int = 0
    scan_truncated: bool = False


# High-confidence content hits: never bypassable via allow_secrets (H1 review).
_HARD_CONTENT_KINDS = frozenset(
    {
        "github_token",
        "aws_access_key",
        "private_key",
        "stripe_key",
        "slack_token",
    }
)


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


def _should_skip_dir(name: str) -> bool:
    """
    Directories never walked on the *fallback* filesystem path.

    Only skip known heavy/vendor dirs and ``.git``. Do **not** skip every
    ``.*`` name — ``.github/``, ``.config/`` etc. are often committed (H1).
    """
    if name == ".git":
        return True
    return name in _SKIP_DIRS


def list_publishable_relpaths(folder: Path) -> tuple[list[str], list[str]]:
    """
    Relative posix paths that would be included by ``git add -A`` (H1).

    Prefer git's view (respects .gitignore). Fallback: filesystem walk that
    still includes ``.github/`` and other dotdirs except ``.git``.
    Returns (paths, warnings).
    """
    root = folder.resolve()
    warnings: list[str] = []
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            from app.git.runner import run_git

            # cached + others, exclude-standard == add -A candidates
            r = run_git(
                [
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                cwd=str(root),
                check=False,
            )
            if r.returncode == 0:
                raw = r.stdout or ""
                paths = [p for p in raw.split("\0") if p]
                # Drop anything under .git if present
                paths = [p for p in paths if not p.startswith(".git/")]
                return paths, warnings
            warnings.append(
                "git ls-files 실패 — 파일시스템 검사로 대체합니다 "
                f"(code={r.returncode})."
            )
        except Exception as e:
            warnings.append(f"git 목록 조회 실패 — 파일시스템 검사: {e}")

    # Fallback walk
    paths: list[str] = []
    for dirpath, dirnames, filenames in os_walk_skip(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel.startswith(".git/"):
                continue
            paths.append(rel)
    return paths, warnings


def find_secret_candidates(
    folder: Path,
    *,
    paths: list[str] | None = None,
) -> list[str]:
    """
    Secret-looking *filenames* among publishable paths only (H1).
    """
    root = folder.resolve()
    if paths is None:
        paths, _ = list_publishable_relpaths(root)
    hits: list[str] = []
    for rel in paths:
        name = Path(rel).name
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


def _email_ignored(addr: str) -> bool:
    low = addr.lower()
    return any(s in low for s in _EMAIL_IGNORE_SUBSTR)


def _iter_text_files(
    root: Path,
    rel_paths: list[str],
    *,
    max_files: int,
) -> tuple[list[tuple[str, str]], bool]:
    """
    Load up to max_files text files from rel_paths.
    Returns ([(rel, text), ...], truncated).
    """
    out: list[tuple[str, str]] = []
    truncated = False
    for i, rel in enumerate(rel_paths):
        if len(out) >= max_files:
            truncated = True
            break
        if i >= max_files * 4 and len(out) == 0:
            # pathological: many binaries first
            truncated = True
            break
        path = root / rel
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in _BINARY_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.append((rel, text))
    if len(rel_paths) > max_files and not truncated:
        # more paths exist than we scanned as text
        if len(out) >= max_files:
            truncated = True
    return out, truncated


def scan_pii_in_contents(
    folder: Path,
    *,
    paths: list[str] | None = None,
) -> list[PiiHit]:
    """
    Scan text file bodies for phone/email among publishable paths (H1).
    """
    root = folder.resolve()
    if paths is None:
        paths, _ = list_publishable_relpaths(root)
    hits: list[PiiHit] = []
    seen: set[tuple[str, str, str]] = set()
    files, _trunc = _iter_text_files(root, paths, max_files=_MAX_FILES_SCANNED)
    for rel, text in files:
        if len(hits) >= _MAX_PII_HITS:
            break
        for m in _PHONE_RE.finditer(text):
            sample = m.group(0)
            key = (rel, "phone", sample)
            if key in seen:
                continue
            seen.add(key)
            hits.append(PiiHit(path=rel, kind="phone", sample=sample))
            if len(hits) >= _MAX_PII_HITS:
                break
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
                break
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


def _mask_secret_sample(raw: str) -> str:
    """Never put full secrets into UI lists."""
    s = (raw or "").strip()
    if not s:
        return "***"
    masked = mask_secrets_in_text(s)
    if masked != s:
        return masked
    if len(s) <= 8:
        return "***"
    return f"{s[:3]}…{s[-2:]} (len={len(s)})"


def scan_secret_in_contents(
    folder: Path,
    *,
    paths: list[str] | None = None,
) -> list[ContentSecretHit]:
    """
    Scan publishable text files for known high-confidence secret shapes (M4/H1).
    """
    root = folder.resolve()
    if paths is None:
        paths, _ = list_publishable_relpaths(root)
    hits: list[ContentSecretHit] = []
    seen: set[tuple[str, str, str]] = set()
    files, _trunc = _iter_text_files(root, paths, max_files=_MAX_FILES_SCANNED)
    for rel, text in files:
        if len(hits) >= _MAX_CONTENT_SECRET_HITS:
            break
        for kind, pattern in _CONTENT_SECRET_PATTERNS:
            for m in pattern.finditer(text):
                sample_raw = m.group(0)
                sample = _mask_secret_sample(sample_raw)
                key = (rel, kind, sample)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(ContentSecretHit(path=rel, kind=kind, sample=sample))
                if len(hits) >= _MAX_CONTENT_SECRET_HITS:
                    break
            if len(hits) >= _MAX_CONTENT_SECRET_HITS:
                break
    return hits


def format_content_secret_list(
    hits: list[ContentSecretHit], *, limit: int = 15
) -> str:
    if not hits:
        return ""
    lines: list[str] = []
    for h in hits[:limit]:
        label = _CONTENT_SECRET_KIND_KO.get(h.kind, h.kind)
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
    allow_secret_filenames: bool | None = None,
    write_gitignore: bool = True,
    scan_pii: bool = True,
) -> SafetyReport:
    """
    Pre-publish safety on *publishable* paths only (H1).

    ``allow_secrets`` / ``allow_secret_filenames``: only bypasses **filename**
    pattern hits. High-confidence **content** secrets (keys, PEM, …) always block.
    """
    if allow_secret_filenames is None:
        allow_secret_filenames = allow_secrets

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

    paths, path_warnings = list_publishable_relpaths(folder)
    report.warnings.extend(path_warnings)
    report.paths_considered = len(paths)
    if len(paths) > _MAX_FILES_SCANNED:
        report.scan_truncated = True
        report.warnings.append(
            f"검사 상한: 내용 스캔은 최대 {_MAX_FILES_SCANNED}개 파일만 합니다 "
            f"(후보 {len(paths)}개). 큰 폴더는 일부만 검사됐을 수 있습니다."
        )

    secrets = find_secret_candidates(folder, paths=paths)
    report.secret_candidates = secrets
    if secrets and not allow_secret_filenames:
        report.ok = False
        report.errors.append(
            "비밀 파일로 보이는 항목이 있습니다. 제거하거나 "
            f"--allow-secrets 로 명시 확인하세요: {', '.join(secrets)}"
        )
    elif secrets:
        report.warnings.append(
            f"--allow-secrets: 다음 파일이 포함될 수 있습니다: {', '.join(secrets)}"
        )

    content_secrets = scan_secret_in_contents(folder, paths=paths)
    report.content_secret_hits = content_secrets
    hard = [h for h in content_secrets if h.kind in _HARD_CONTENT_KINDS]
    soft = [h for h in content_secrets if h.kind not in _HARD_CONTENT_KINDS]
    if hard:
        report.ok = False
        listing = ", ".join(
            f"{h.path}({_CONTENT_SECRET_KIND_KO.get(h.kind, h.kind)})"
            for h in hard[:12]
        )
        report.errors.append(
            "파일 내용에 비밀 키처럼 보이는 값이 있어 막을 수 없습니다 "
            f"(고급 허용으로도 우회 불가): {listing}"
        )
    if soft and not allow_secret_filenames:
        report.ok = False
        listing = ", ".join(
            f"{h.path}({_CONTENT_SECRET_KIND_KO.get(h.kind, h.kind)})"
            for h in soft[:12]
        )
        report.errors.append(
            "파일 내용에 비밀처럼 보이는 값이 있습니다. 제거하거나 "
            f"--allow-secrets 로 명시 확인하세요: {listing}"
        )
    elif soft:
        report.warnings.append(
            f"--allow-secrets: 내용 비밀 후보(완화) {len(soft)}건이 포함될 수 있습니다."
        )

    if scan_pii:
        pii = scan_pii_in_contents(folder, paths=paths)
        report.pii_hits = pii
        if pii:
            report.warnings.append(
                f"파일 내용에서 개인정보로 보이는 패턴 {len(pii)}건 "
                f"(전화/이메일). 업로드 전 확인하세요."
            )

    return report
