"""Send update-manager diagnosis to the CloneUp GitHub repo as an Issue."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from app.auth.token_store import load_token
from app.ui.settings_store import (
    load_um_diag_last_signature,
    load_um_diag_last_sent_epoch,
    load_um_diag_report_enabled,
    save_um_diag_last_signature,
    save_um_diag_last_sent_epoch,
)
from app.util.update_manager_health import (
    DIAG_OWNER,
    DIAG_REPO,
    UpdateManagerHealth,
    build_diagnostic_markdown,
    issue_title,
    pending_diag_path,
    probe_update_manager,
)

log = logging.getLogger("cloneup.um_diag")

# At most one auto-issue per signature per this many seconds.
_MIN_RESEND_SEC = 24 * 3600
_API = f"https://api.github.com/repos/{DIAG_OWNER}/{DIAG_REPO}/issues"
_UA = "CloneUp-Tray-UMDiag/0.1"


@dataclass(frozen=True)
class DiagSendResult:
    status: str  # skipped_ok | skipped_disabled | skipped_rate | filed | saved_local | error
    detail: str = ""
    issue_url: str = ""


def should_consider_report(health: UpdateManagerHealth) -> bool:
    if health.ok:
        return False
    # If we only lack Run key but process is running with no log errors — soft.
    if health.problems == ["run_key_missing"] and health.process_running:
        return False
    return True


def _rate_limited(signature: str) -> bool:
    last_sig = load_um_diag_last_signature() or ""
    last_ts = load_um_diag_last_sent_epoch()
    if last_sig == signature and last_ts > 0:
        if (time.time() - last_ts) < _MIN_RESEND_SEC:
            return True
    return False


def _mark_sent(signature: str) -> None:
    save_um_diag_last_signature(signature)
    save_um_diag_last_sent_epoch(int(time.time()))


def _save_pending(body: str) -> Path:
    path = pending_diag_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _create_github_issue(token: str, title: str, body: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": _UA,
    }
    payload = {
        "title": title[:200],
        "body": body[:60000],
        "labels": ["update-manager-diag", "auto-report"],
    }
    # Labels may 422 if they don't exist yet — retry without labels.
    resp = requests.post(_API, headers=headers, json=payload, timeout=45)
    if resp.status_code == 422 and "label" in (resp.text or "").lower():
        payload.pop("labels", None)
        resp = requests.post(_API, headers=headers, json=payload, timeout=45)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {(resp.text or '')[:400]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("unexpected issue response")
    return data


def new_issue_browser_url(title: str, body: str) -> str:
    """Fallback deep-link (body truncated for URL length)."""
    short = body if len(body) < 3500 else body[:3500] + "\n\n…(truncated)"
    return (
        f"https://github.com/{DIAG_OWNER}/{DIAG_REPO}/issues/new"
        f"?title={quote(title)}&body={quote(short)}"
    )


def run_um_diag_cycle(*, attempt_restart: bool = True) -> DiagSendResult:
    """
    Probe update manager; if unhealthy, file a GitHub issue (or save locally).

    Safe to call from a worker thread (uses requests + disk only).
    """
    if not load_um_diag_report_enabled():
        return DiagSendResult("skipped_disabled", "setting off")

    health = probe_update_manager(attempt_restart=attempt_restart)
    if not should_consider_report(health):
        return DiagSendResult("skipped_ok", "healthy or soft-only")

    if _rate_limited(health.signature):
        return DiagSendResult(
            "skipped_rate",
            f"already reported {health.signature} within {_MIN_RESEND_SEC}s",
        )

    title = issue_title(health)
    body = build_diagnostic_markdown(health)
    # Stamp so pending files are identifiable even if send fails.
    body = (
        f"<!-- cloneup-um-diag {health.signature} "
        f"{datetime.now(timezone.utc).isoformat()} -->\n\n" + body
    )

    pending = _save_pending(body)
    token = (load_token() or "").strip()
    if not token:
        url = new_issue_browser_url(title, body)
        return DiagSendResult(
            "saved_local",
            f"no GitHub token; wrote {pending}",
            issue_url=url,
        )

    try:
        data = _create_github_issue(token, title, body)
        url = str(data.get("html_url") or "")
        _mark_sent(health.signature)
        log.info("filed update-manager diag issue: %s", url)
        return DiagSendResult("filed", f"issue #{data.get('number')}", issue_url=url)
    except Exception as e:
        log.warning("could not file GitHub issue: %s", e)
        url = new_issue_browser_url(title, body)
        return DiagSendResult(
            "saved_local",
            f"API failed ({e}); wrote {pending}",
            issue_url=url,
        )
