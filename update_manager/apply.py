"""
Download release zip and file-copy into the CloneUp install dir.

Does **not** run CloneUp-Setup.exe (that would show the installer GUI).
Mirrors what Inno ``[Files]`` does: replace onedir contents in place.

Download resilience (Tier 1 — industry-aligned, urllib only)
----------------------------------------------------------
Intra-call Range resume only: ``.part`` survives timeouts *inside one*
``download_asset`` invocation. Cross-tick / defer persistence is Tier 2
(persistent pending dir) — do not market Tier 1 as full “이어받기”.

Attempt budget is a **single** loop (``_DOWNLOAD_MAX_ATTEMPTS``). There is
no outer “3 full-file retries × inner 8” multiplication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from update_manager.config import USER_AGENT
from update_manager.github_release import LatestRelease, host_allowed
from update_manager.versioning import version_tuple_to_str

log = logging.getLogger("cloneup_update_manager")

# CloneUp-win64.zip is ~200MB+. Stall mid-read used to wipe progress.
_DOWNLOAD_TIMEOUT_SEC = 900
# Single budget for connect failures + mid-stream resume retries (replaces
# the old “3 full-file retries” — not nested with another counter).
_DOWNLOAD_MAX_ATTEMPTS = 8
_ZERO_PROGRESS_ABORT_AFTER = 3
_REPLACE_RETRIES = 5
# Tier 1b: last 5 zip-bearing releases (0.1.9–0.1.13) all publish digest →
# refuse apply when API omits digest (fail-closed).
_REQUIRE_DIGEST = True
_DISK_MARGIN_BYTES = 8 * 1024 * 1024


def _ssl_context():
    import ssl

    return ssl.create_default_context()


def _part_path(dest: Path) -> Path:
    return Path(str(dest) + ".part")


def _meta_path(dest: Path) -> Path:
    return Path(str(dest) + ".part.meta")


def _load_meta(dest: Path) -> dict:
    path = _meta_path(dest)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_meta(dest: Path, meta: dict) -> None:
    path = _meta_path(dest)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")


def _clear_partial(dest: Path) -> None:
    for p in (_part_path(dest), _meta_path(dest)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_content_range(header: str | None) -> tuple[int | None, int | None, int | None]:
    """Return (start, end, total) from Content-Range, or Nones if unusable."""
    if not header:
        return None, None, None
    # bytes start-end/total  or  bytes */total
    m = re.match(
        r"bytes\s+(\d+)\s*-\s*(\d+)\s*/\s*(\d+|\*)",
        header.strip(),
        re.I,
    )
    if not m:
        return None, None, None
    start = int(m.group(1))
    end = int(m.group(2))
    total_s = m.group(3)
    total = None if total_s == "*" else int(total_s)
    return start, end, total


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def _ensure_disk_space(dest: Path, expected_total: int | None) -> None:
    if not expected_total or expected_total <= 0:
        return
    try:
        free = shutil.disk_usage(dest.parent).free
    except OSError as e:
        log.warning("disk_usage failed: %s", e)
        return
    need = expected_total + _DISK_MARGIN_BYTES
    if free < need:
        raise RuntimeError(
            f"insufficient disk space: need ~{need} bytes, free {free} "
            f"(ENOSPC burns download attempts until hard fail)"
        )


def _atomic_replace(part: Path, dest: Path) -> None:
    """os.replace with short retries — Windows AV often locks a just-closed file."""
    last: BaseException | None = None
    for i in range(1, _REPLACE_RETRIES + 1):
        try:
            os.replace(str(part), str(dest))
            return
        except PermissionError as e:
            last = e
            log.warning("replace attempt %s/%s PermissionError: %s", i, _REPLACE_RETRIES, e)
            time.sleep(0.2 * i)
        except OSError as e:
            last = e
            # Cross-volume rare here; fall through
            if getattr(e, "winerror", None) == 17 or e.errno == 18:
                shutil.copy2(part, dest)
                part.unlink(missing_ok=True)
                return
            log.warning("replace attempt %s/%s OSError: %s", i, _REPLACE_RETRIES, e)
            time.sleep(0.2 * i)
    raise RuntimeError(f"could not finalize download (file locked?): {last}")


def download_asset(url: str, dest: Path, *, digest: str | None = None) -> None:
    """
    Download ``url`` to ``dest`` with intra-call Range resume.

    Tier 1 only: ``.part`` is reused across attempts *inside this call*.
    Callers that wipe the parent temp dir between ticks still start over
    (cross-tick resume = Tier 2).
    """
    if not url.startswith("https://") or not host_allowed(url):
        raise RuntimeError(f"refusing download host: {url!r}")
    if _REQUIRE_DIGEST and not (digest and str(digest).strip()):
        raise RuntimeError(
            "release asset digest missing — refuse download (fail-closed; "
            "last 5 CloneUp-win64.zip releases publish sha256)"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = _part_path(dest)
    meta = _load_meta(dest)
    expected_total: int | None = meta.get("expected_total")
    if isinstance(expected_total, int) and expected_total <= 0:
        expected_total = None
    etag = str(meta.get("etag") or "").strip() or None
    last_mod = str(meta.get("last_modified") or "").strip() or None

    last_err: BaseException | None = None
    zero_progress_streak = 0
    completed = False

    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        resume_from = part.stat().st_size if part.is_file() else 0
        size_before = resume_from
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream",
        }
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
            if etag:
                headers["If-Range"] = etag
            elif last_mod:
                # Weaker than ETag (second precision); prefer digest at end.
                headers["If-Range"] = last_mod
                log.warning(
                    "resume with Last-Modified If-Range only (no ETag) — "
                    "integrity relies on digest/size; hot-redeploys may collide"
                )
            else:
                log.warning(
                    "resume without ETag/Last-Modified — size/digest only"
                )

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(
                req, context=_ssl_context(), timeout=_DOWNLOAD_TIMEOUT_SEC
            ) as resp:
                final = resp.geturl()
                if not host_allowed(final):
                    raise RuntimeError(f"redirect to disallowed host: {final!r}")
                status = int(getattr(resp, "status", None) or resp.getcode())
                hdrs = resp.headers

                mode = "wb"
                if resume_from > 0:
                    if status == 200:
                        # Range ignored or If-Range failed → never append
                        log.info(
                            "server returned 200 on resume (Range ignored or "
                            "resource changed) — restarting from byte 0"
                        )
                        part.unlink(missing_ok=True)
                        resume_from = 0
                        etag = None
                        last_mod = None
                        expected_total = None
                        mode = "wb"
                    elif status == 206:
                        cr = hdrs.get("Content-Range")
                        start, _end, total = _parse_content_range(cr)
                        if cr is None or start is None:
                            # Unsafe 206 without Content-Range (yt-dlp posture)
                            log.warning(
                                "206 without usable Content-Range — restart from 0"
                            )
                            part.unlink(missing_ok=True)
                            resume_from = 0
                            mode = "wb"
                        elif start != resume_from:
                            log.warning(
                                "Content-Range start %s != resume_from %s — restart",
                                start,
                                resume_from,
                            )
                            part.unlink(missing_ok=True)
                            resume_from = 0
                            mode = "wb"
                        else:
                            mode = "ab"
                            if total is not None:
                                expected_total = total
                    elif status == 416:
                        if expected_total and resume_from >= expected_total:
                            completed = True
                            break
                        log.warning("HTTP 416 on resume — clearing partial")
                        part.unlink(missing_ok=True)
                        resume_from = 0
                        mode = "wb"
                    else:
                        raise RuntimeError(f"unexpected HTTP status on resume: {status}")
                else:
                    if status != 200:
                        raise RuntimeError(f"unexpected HTTP status: {status}")
                    mode = "wb"
                    cl = hdrs.get("Content-Length")
                    if cl and cl.isdigit():
                        expected_total = int(cl)
                    etag = (hdrs.get("ETag") or "").strip() or etag
                    last_mod = (hdrs.get("Last-Modified") or "").strip() or last_mod

                _ensure_disk_space(dest, expected_total)
                _save_meta(
                    dest,
                    {
                        "etag": etag,
                        "last_modified": last_mod,
                        "expected_total": expected_total,
                        "url": url,
                    },
                )

                with part.open(mode) as out:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)

            # Stream finished without exception
            size_after = part.stat().st_size if part.is_file() else 0
            if size_after <= size_before:
                zero_progress_streak += 1
            else:
                zero_progress_streak = 0

            if expected_total is not None and size_after < expected_total:
                raise RuntimeError(
                    f"incomplete download: got {size_after} of {expected_total} bytes"
                )

            completed = True
            break

        except (TimeoutError, OSError, urllib.error.URLError, RuntimeError) as e:
            last_err = e
            size_after = part.stat().st_size if part.is_file() else 0
            if size_after <= size_before:
                zero_progress_streak += 1
            else:
                zero_progress_streak = 0
            log.warning(
                "download attempt %s/%s failed (resume_from=%s, bytes=%s): %s",
                attempt,
                _DOWNLOAD_MAX_ATTEMPTS,
                resume_from,
                size_after,
                e,
            )
            if zero_progress_streak >= _ZERO_PROGRESS_ABORT_AFTER:
                _clear_partial(dest)
                raise RuntimeError(
                    f"download stalled with no progress for "
                    f"{zero_progress_streak} attempts: {e}"
                ) from e
            if attempt >= _DOWNLOAD_MAX_ATTEMPTS:
                break
            # Disk full burns the attempt budget until hard fail (space rarely frees itself).
            if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
                log.error(
                    "ENOSPC during download — each retry consumes attempt budget; "
                    "will hard-fail when attempts are exhausted unless space is freed"
                )
            time.sleep(min(30, 5 * attempt))
            continue

    if not completed or not part.is_file():
        raise RuntimeError(
            f"download failed after {_DOWNLOAD_MAX_ATTEMPTS} attempts: {last_err}"
        )

    final_size = part.stat().st_size
    if expected_total is not None and final_size != expected_total:
        _clear_partial(dest)
        raise RuntimeError(
            f"size mismatch after download: got {final_size}, expected {expected_total}"
        )

    got_hash = _sha256_file(part)
    if digest:
        expect = str(digest).split(":", 1)[-1].strip().lower()
        if expect and got_hash != expect:
            _clear_partial(dest)
            raise RuntimeError(
                f"digest mismatch: expected {expect[:12]}… got {got_hash[:12]}…"
            )
        log.info("integrity=sha256 ok")
    else:
        log.info("integrity=size-only (no digest)")

    dest.unlink(missing_ok=True)
    _atomic_replace(part, dest)
    try:
        _meta_path(dest).unlink(missing_ok=True)
    except OSError:
        pass
    log.info(
        "download complete %s bytes (attempts used ≤ %s)",
        final_size,
        _DOWNLOAD_MAX_ATTEMPTS,
    )


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
        "applied %s into %s",
        version_tuple_to_str(release.version),
        install_dir,
    )
