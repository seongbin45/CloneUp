"""Untrack oversized paths without deleting working-tree files (plan rev.3).

IMPORTANT: always ``git rm --cached`` (not ``git rm``) so Release upload (S4)
can still read the original bytes from disk.
"""

from __future__ import annotations

from pathlib import Path

from app.git.large_files import gitignore_exact_line
from app.git.runner import GitError, run_git


class UntrackError(Exception):
    """Beginner-facing untrack failure."""


def append_exact_gitignore(folder: Path, rels: list[str]) -> list[str]:
    """Append ``/<rel>`` lines; return lines that were newly added."""
    root = folder.resolve()
    gi = root / ".gitignore"
    existing = ""
    if gi.is_file():
        try:
            existing = gi.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise UntrackError(f".gitignore를 읽지 못했습니다: {e}") from e
    have = {ln.strip() for ln in existing.splitlines()}
    added: list[str] = []
    for rel in rels:
        line = gitignore_exact_line(rel)
        if line in have:
            continue
        added.append(line)
        have.add(line)
    if not added:
        return []
    try:
        with gi.open("a", encoding="utf-8", newline="\n") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            if existing and not existing.rstrip().endswith("# CloneUp large files"):
                f.write("\n# CloneUp large files\n")
            elif not existing:
                f.write("# CloneUp large files\n")
            for line in added:
                f.write(f"{line}\n")
    except OSError as e:
        raise UntrackError(f".gitignore에 쓰지 못했습니다: {e}") from e
    return added


def untrack_worktree(
    folder: Path,
    rels: list[str],
    *,
    commit: bool = True,
    message: str = "큰 파일 제외",
) -> None:
    """U-worktree: exact gitignore + ``git rm --cached`` + optional commit."""
    root = folder.resolve()
    if not rels:
        return
    append_exact_gitignore(root, rels)
    # rm --cached keeps disk files (required for later Release upload).
    args = ["rm", "-f", "--cached", "--", *[r.replace("\\", "/") for r in rels]]
    r = run_git(args, cwd=str(root), check=False)
    # Some paths may be untracked already — still OK if gitignore was written.
    if r.returncode not in (0, 1) and "did not match" not in (
        (r.stderr or "") + (r.stdout or "")
    ).lower():
        # Continue if only some failed; raise on hard errors
        err = (r.stderr or r.stdout or "").strip()
        if "fatal" in err.lower():
            raise UntrackError(f"추적 해제 실패: {err[:400]}") from None
    if not commit:
        return
    run_git(["add", "--", ".gitignore"], cwd=str(root), check=False)
    # Stage rm results already in index
    st = run_git(["diff", "--cached", "--quiet"], cwd=str(root), check=False)
    if st.returncode == 0:
        return  # nothing to commit
    run_git(["commit", "-m", message], cwd=str(root), check=True)


def resolve_upstream_ref(folder: Path) -> str:
    """Return abbrev upstream ref (e.g. ``origin/main``) via ``@{upstream}``."""
    r = run_git(
        ["rev-parse", "--abbrev-ref", "@{upstream}"],
        cwd=str(folder),
        check=False,
    )
    if r.returncode != 0:
        raise UntrackError(
            "비교할 원격 갈래를 찾지 못했습니다.\n"
            "아직 GitHub에 올린 적이 없거나, 추적 원격이 없습니다."
        )
    ref = (r.stdout or "").strip()
    if not ref or ref == "@{upstream}":
        raise UntrackError("원격 갈래 이름이 비어 있습니다.")
    return ref


def upstream_has_commits(folder: Path) -> bool:
    """True if ``@{upstream}`` resolves to a commit."""
    r = run_git(
        ["rev-parse", "--verify", "@{upstream}"],
        cwd=str(folder),
        check=False,
    )
    return r.returncode == 0


def count_commits_ahead_of_upstream(folder: Path) -> int | None:
    """Number of local commits not on upstream; None if no upstream."""
    if not upstream_has_commits(folder):
        return None
    r = run_git(
        ["rev-list", "--count", "@{upstream}..HEAD"],
        cwd=str(folder),
        check=False,
    )
    if r.returncode != 0:
        return None
    try:
        return int((r.stdout or "0").strip() or "0")
    except ValueError:
        return None


def untrack_after_soft_reset(
    folder: Path,
    rels: list[str],
    *,
    message: str = "큰 파일 제외",
) -> None:
    """U-hist: fetch → reset --soft @{upstream} → rm --cached → one commit.

    Squashes unpushed commits into one exclusion commit (disclose in UI, L-12).
    Never force-pushes.
    """
    root = folder.resolve()
    if not rels:
        return
    # Refresh upstream tip so reset target is current (avoid non-FF later).
    fetch = run_git(["fetch", "--prune"], cwd=str(root), check=False)
    if fetch.returncode != 0:
        # Non-fatal if offline — still try with cached upstream
        pass
    upstream = resolve_upstream_ref(root)
    try:
        run_git(["reset", "--soft", upstream], cwd=str(root), check=True)
    except GitError as e:
        raise UntrackError(
            "원격과 맞추는 중 문제가 생겼습니다.\n"
            f"{e}"
        ) from e
    append_exact_gitignore(root, rels)
    args = ["rm", "-f", "--cached", "--", *[r.replace("\\", "/") for r in rels]]
    r = run_git(args, cwd=str(root), check=False)
    if r.returncode not in (0, 1):
        err = (r.stderr or r.stdout or "").strip()
        if "fatal" in err.lower():
            raise UntrackError(f"추적 해제 실패: {err[:400]}")
    run_git(["add", "--", ".gitignore"], cwd=str(root), check=False)
    st = run_git(["diff", "--cached", "--quiet"], cwd=str(root), check=False)
    if st.returncode == 0:
        # Still create empty? Prefer no-op message
        return
    try:
        run_git(["commit", "-m", message], cwd=str(root), check=True)
    except GitError as e:
        raise UntrackError(f"제외 기록을 남기지 못했습니다:\n{e}") from e
