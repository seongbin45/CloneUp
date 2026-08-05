"""Pre-publish safety checks for beginner-friendly defaults."""

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


@dataclass
class SafetyReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    secret_candidates: list[str] = field(default_factory=list)
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

    return report
