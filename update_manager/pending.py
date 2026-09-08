"""Persistent pending zip staging (Tier 2)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from update_manager.apply import _sha256_file, download_asset
from update_manager.github_release import LatestRelease
from update_manager.paths import manager_mode, pending_root, pending_version_dir
from update_manager.versioning import version_tuple_to_str

log = logging.getLogger("cloneup_update_manager")


def _meta_path(pend: Path) -> Path:
    return pend / "meta.json"


def load_meta(pend: Path) -> dict[str, Any]:
    p = _meta_path(pend)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_meta(pend: Path, meta: dict[str, Any]) -> None:
    pend.mkdir(parents=True, exist_ok=True)
    path = _meta_path(pend)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(str(tmp), str(path))


def is_reparse_point(path: Path) -> bool:
    if not path.exists():
        return False
    if sys_platform_is_win():
        try:
            import ctypes
            from ctypes import wintypes

            GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
            GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
            GetFileAttributesW.restype = wintypes.DWORD
            attrs = GetFileAttributesW(str(path))
            if attrs == 0xFFFFFFFF:
                return False
            # FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            return bool(attrs & 0x400)
        except Exception:
            return False
    return path.is_symlink()


def sys_platform_is_win() -> bool:
    import sys

    return sys.platform == "win32"


def safe_remove_tree(path: Path) -> None:
    """Remove path; never rmtree through a junction (follow-into wipe risk)."""
    if not path.exists() and not is_reparse_point(path):
        return
    if is_reparse_point(path):
        try:
            os.rmdir(path)  # removes junction only
        except OSError as e:
            raise RuntimeError(f"cannot remove reparse point {path}: {e}") from e
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def ensure_pending_acl(pend: Path) -> None:
    from update_manager.acl_win import ensure_dir_acl

    mode = "machine" if manager_mode() == "machine" else "user"
    ensure_dir_acl(pending_root(), mode=mode)
    ensure_dir_acl(pend, mode=mode)


def zip_path(pend: Path, asset_name: str) -> Path:
    return pend / asset_name


def zip_ok_idle(pend: Path, release: LatestRelease) -> bool:
    """True if complete zip present and idle cache says verified (no re-hash)."""
    zp = zip_path(pend, release.asset_name)
    if not zp.is_file():
        return False
    meta = load_meta(pend)
    digest = (release.digest or "").split(":", 1)[-1].strip().lower()
    try:
        st = zp.stat()
    except OSError:
        return False
    if (
        meta.get("zip_sha256")
        and meta.get("zip_size") == st.st_size
        and meta.get("zip_mtime_ns") == getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        and str(meta.get("digest") or "").split(":", 1)[-1].strip().lower() == digest
    ):
        return True
    return False


def record_zip_verified(pend: Path, release: LatestRelease, sha256_hex: str) -> None:
    zp = zip_path(pend, release.asset_name)
    st = zp.stat()
    meta = load_meta(pend)
    meta.update(
        {
            "tag": release.tag,
            "asset_name": release.asset_name,
            "digest": release.digest,
            "download_url": release.download_url,
            "zip_sha256": sha256_hex,
            "zip_size": st.st_size,
            "zip_mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
            "verified_at": time.time(),
        }
    )
    save_meta(pend, meta)


def verify_zip_full(pend: Path, release: LatestRelease) -> str:
    """Apply-gate: always re-hash. Returns hex digest. Raises on mismatch."""
    zp = zip_path(pend, release.asset_name)
    if not zp.is_file():
        raise RuntimeError("pending zip missing at apply gate")
    got = _sha256_file(zp)
    expect = (release.digest or "").split(":", 1)[-1].strip().lower()
    if not expect or got != expect:
        # Wipe bad content
        zp.unlink(missing_ok=True)
        Path(str(zp) + ".part").unlink(missing_ok=True)
        Path(str(zp) + ".part.meta").unlink(missing_ok=True)
        raise RuntimeError(
            f"apply-gate digest mismatch: expected {expect[:12]}… got {got[:12]}…"
        )
    record_zip_verified(pend, release, got)
    return got


def ensure_zip(pend: Path, release: LatestRelease) -> None:
    """Download/resume zip into pending if idle cache miss."""
    ensure_pending_acl(pend)
    meta = load_meta(pend)
    meta.update(
        {
            "tag": release.tag,
            "asset_name": release.asset_name,
            "digest": release.digest,
            "download_url": release.download_url,
        }
    )
    save_meta(pend, meta)
    if zip_ok_idle(pend, release):
        log.info("pending zip cache hit %s", release.asset_name)
        return
    zp = zip_path(pend, release.asset_name)
    # Corrupt / incomplete final zip → remove so download_asset starts clean
    if zp.is_file() and not zip_ok_idle(pend, release):
        # May still have valid .part from interrupted download — only remove
        # complete zip if hash would fail; leave .part for resume.
        try:
            if zp.stat().st_size > 0:
                # If no matching cache, treat complete-looking file as suspect
                # unless .part exists (resume in progress uses .part not zip)
                pass
        except OSError:
            pass
        # If .part exists, download_asset resumes; if only bad zip, delete zip
        part = Path(str(zp) + ".part")
        if not part.is_file():
            zp.unlink(missing_ok=True)
    download_asset(release.download_url, zp, digest=release.digest)
    # Record idle cache after successful download (hash already checked inside)
    expect = (release.digest or "").split(":", 1)[-1].strip().lower()
    record_zip_verified(pend, release, expect)


def ensure_extract(pend: Path, release: LatestRelease) -> Path:
    """Extract onedir; return root containing CloneUp.exe."""
    from update_manager.apply import _find_onedir_root

    extract_dir = pend / "extract"
    complete = extract_dir / ".complete"
    digest = (release.digest or "").split(":", 1)[-1].strip().lower()

    if extract_dir.exists() or is_reparse_point(extract_dir):
        if is_reparse_point(extract_dir):
            log.warning("extract path is reparse — removing junction only")
            safe_remove_tree(extract_dir)
        elif complete.is_file():
            try:
                if complete.read_text(encoding="utf-8").strip().lower() == digest:
                    root = _find_onedir_root(extract_dir)
                    if (root / "CloneUp.exe").is_file():
                        return root
            except OSError:
                pass
            safe_remove_tree(extract_dir)
        else:
            safe_remove_tree(extract_dir)

    if is_reparse_point(extract_dir):
        raise RuntimeError("extract path still reparse after cleanup")
    extract_dir.mkdir(parents=True, exist_ok=True)

    zp = zip_path(pend, release.asset_name)
    with zipfile.ZipFile(zp, "r") as zf:
        zf.extractall(extract_dir)
    root = _find_onedir_root(extract_dir)
    if not (root / "CloneUp.exe").is_file():
        safe_remove_tree(extract_dir)
        raise RuntimeError("extract missing CloneUp.exe")
    complete.write_text(digest + "\n", encoding="utf-8")
    return root


def prune_other_versions(keep_version: str) -> None:
    root = pending_root()
    if not root.is_dir():
        return
    keep = keep_version.strip()
    for child in list(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == keep:
            continue
        try:
            safe_remove_tree(child)
            log.info("pruned pending version %s", child.name)
        except OSError as e:
            log.warning("prune failed %s: %s", child, e)


def delete_version_dir(pend: Path) -> None:
    try:
        safe_remove_tree(pend)
    except OSError as e:
        log.warning("could not delete pending %s: %s", pend, e)
