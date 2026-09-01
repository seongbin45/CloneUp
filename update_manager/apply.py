"""
Download release zip and file-copy into the CloneUp install dir.

Does **not** run CloneUp-Setup.exe (that would show the installer GUI).
Mirrors what Inno ``[Files]`` does: replace onedir contents in place.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from update_manager.config import USER_AGENT
from update_manager.github_release import LatestRelease, host_allowed
from update_manager.versioning import version_tuple_to_str

log = logging.getLogger("cloneup_update_manager")


def _ssl_context():
    import ssl

    return ssl.create_default_context()


def download_asset(url: str, dest: Path, *, digest: str | None = None) -> None:
    if not url.startswith("https://") or not host_allowed(url):
        raise RuntimeError(f"refusing download host: {url!r}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"},
        method="GET",
    )
    h = hashlib.sha256()
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=300) as resp:
        final = resp.geturl()
        if not host_allowed(final):
            raise RuntimeError(f"redirect to disallowed host: {final!r}")
        with dest.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                h.update(chunk)
                out.write(chunk)
    if digest:
        # GitHub format: "sha256:hex"
        expect = digest.split(":", 1)[-1].strip().lower()
        got = h.hexdigest().lower()
        if expect and got != expect:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"digest mismatch: expected {expect[:12]}… got {got[:12]}…")


def _find_onedir_root(extract_dir: Path) -> Path:
    """
    Zip may be ``CloneUp/CloneUp.exe`` or flat ``CloneUp.exe`` at root.
    """
    direct = extract_dir / "CloneUp.exe"
    if direct.is_file():
        return extract_dir
    nested = extract_dir / "CloneUp"
    if (nested / "CloneUp.exe").is_file():
        return nested
    # Search one level
    for child in extract_dir.iterdir():
        if child.is_dir() and (child / "CloneUp.exe").is_file():
            return child
    raise RuntimeError("zip does not contain CloneUp.exe")


def _preserve_name(name: str) -> bool:
    """Keep Inno uninstaller files so Apps & Features removal still works."""
    return name.lower().startswith("unins")


def _clear_dir_contents(folder: Path, *, preserve_unins: bool = True) -> None:
    """Remove files/dirs inside folder but keep folder itself (and optional unins*)."""
    if not folder.is_dir():
        return
    for child in list(folder.iterdir()):
        if preserve_unins and _preserve_name(child.name):
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=False)
            else:
                child.unlink(missing_ok=True)
        except OSError as e:
            log.warning("could not remove %s: %s", child, e)
            raise


def copy_onedir_into(src_root: Path, install_dir: Path) -> None:
    """
    Replace install_dir contents with src_root (Inno-like file copy).

    Keeps install_dir path stable (Start Menu / ARP still valid).
    Preserves ``unins*`` so the existing Inno uninstaller keeps working.
    """
    install_dir.mkdir(parents=True, exist_ok=True)
    # Wipe then copy — same effect as ignoreversion recursesubdirs overwrite.
    _clear_dir_contents(install_dir, preserve_unins=True)
    for item in src_root.iterdir():
        if _preserve_name(item.name):
            continue
        dest = install_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    # Ensure VERSION file exists for next check.
    ver_src = src_root / "VERSION"
    if ver_src.is_file():
        shutil.copy2(ver_src, install_dir / "VERSION")


def stage_zip_update(release: LatestRelease, staging_dir: Path) -> Path:
    """
    Download + extract zip into ``staging_dir``; return onedir root with CloneUp.exe.

    Call this **before** killing CloneUp so a failed download leaves the app running.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    zip_path = staging_dir / release.asset_name
    log.info(
        "downloading %s (%s) → %s",
        release.asset_name,
        version_tuple_to_str(release.version),
        zip_path,
    )
    download_asset(release.download_url, zip_path, digest=release.digest)
    extract_dir = staging_dir / "extract"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    src = _find_onedir_root(extract_dir)
    if not (src / "CloneUp.exe").is_file():
        raise RuntimeError("staged update missing CloneUp.exe")
    return src


def install_staged_onedir(src_root: Path, install_dir: Path) -> None:
    """File-copy a previously staged onedir into the live install dir."""
    log.info("file-copy %s → %s", src_root, install_dir)
    copy_onedir_into(src_root, install_dir)


def apply_zip_update(release: LatestRelease, install_dir: Path) -> None:
    """Download zip and install (used by tests; production prefers stage-then-kill)."""
    with tempfile.TemporaryDirectory(prefix="cloneup_upd_") as tmp:
        src = stage_zip_update(release, Path(tmp))
        install_staged_onedir(src, install_dir)
    log.info(
        "updated install dir to %s",
        version_tuple_to_str(release.version),
    )
