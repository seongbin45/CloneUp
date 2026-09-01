"""Fetch latest GitHub release metadata (zip asset only — never Setup.exe)."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from update_manager.config import (
    API_LATEST,
    ASSET_NAME_CANDIDATES,
    USER_AGENT,
)
from update_manager.versioning import normalize_version

log = logging.getLogger("cloneup_update_manager")

# Hosts allowed for download redirects.
_ALLOWED_HOST_SUFFIXES = (
    "github.com",
    "githubusercontent.com",
)


@dataclass(frozen=True)
class LatestRelease:
    tag: str
    version: tuple[int, int, int]
    asset_name: str
    download_url: str
    digest: str | None  # e.g. "sha256:abcd..."


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def fetch_latest_release(*, etag: str | None = None) -> LatestRelease | None:
    """
    Return latest release with a zip asset, or None if unchanged / unavailable.

    Raises nothing for network errors — returns None and logs.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if etag:
        headers["If-None-Match"] = etag
    req = urllib.request.Request(API_LATEST, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=45) as resp:
            if resp.status == 304:
                return None
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None
        log.warning("github latest HTTP %s", e.code)
        return None
    except Exception as e:
        log.warning("github latest failed: %s", e)
        return None

    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    ver = normalize_version(tag)
    if ver is None:
        log.warning("unparseable release tag: %r", tag)
        return None

    assets = data.get("assets") or []
    by_name = {
        str(a.get("name") or ""): a for a in assets if isinstance(a, dict)
    }
    chosen = None
    for name in ASSET_NAME_CANDIDATES:
        if name in by_name:
            chosen = by_name[name]
            break
    if chosen is None:
        # Fallback: any .zip whose name starts with CloneUp
        for name, a in by_name.items():
            lower = name.lower()
            if lower.endswith(".zip") and "cloneup" in lower and "setup" not in lower:
                chosen = a
                break
    if chosen is None:
        log.warning(
            "no zip asset on release %s (need %s) — refusing Setup.exe",
            tag,
            ", ".join(ASSET_NAME_CANDIDATES),
        )
        return None

    url = str(
        chosen.get("browser_download_url") or chosen.get("url") or ""
    ).strip()
    if not url.startswith("https://"):
        log.warning("bad asset url: %r", url)
        return None
    digest = chosen.get("digest")
    digest_s = str(digest).strip() if digest else None
    return LatestRelease(
        tag=tag,
        version=ver,
        asset_name=str(chosen.get("name") or ""),
        download_url=url,
        digest=digest_s or None,
    )


def host_allowed(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == s or host.endswith("." + s) for s in _ALLOWED_HOST_SUFFIXES)
