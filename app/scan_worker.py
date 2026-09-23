"""Headless project-scan worker (schtasks / ``python -m app.scan_worker``).

Fresh-reads QSettings each run (C-12). No Qt widgets.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or "."
    d = Path(base) / "CloneUp" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "scan_worker.log"


def _setup_logging() -> logging.Logger:
    log = logging.getLogger("cloneup.scan_worker")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        fh = RotatingFileHandler(
            _log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        log.addHandler(fh)
    except OSError:
        log.addHandler(logging.StreamHandler(sys.stderr))
    return log


def run_scan_worker(*, force_full: bool = False) -> int:
    """Return process exit code (0 = ok / skipped)."""
    log = _setup_logging()

    # Import after path setup — Qt Core only via settings_store
    try:
        from app.ui.settings_store import load_bg_project_scan_enabled
    except Exception as e:  # noqa: BLE001
        log.error("settings import failed: %s", e)
        return 1

    # C-12: fresh-read every run
    if not load_bg_project_scan_enabled():
        log.info("bg_project_scan disabled — exit")
        return 0

    from app.git.project_scan import scan_projects_incremental
    from app.git.scan_cache import ScanCacheLock, save_scan_cache

    t0 = time.monotonic()
    lock = ScanCacheLock(timeout_sec=0.0)
    if not lock.acquire():
        log.info("cache lock busy — skip this run")
        return 0
    try:
        entries, partial, cache = scan_projects_incremental(
            force_full=force_full,
            probe_dirty=False,
            skip_unc=True,
        )
        cache.generator = "worker"
        ok = save_scan_cache(cache)
        log.info(
            "scan done entries=%s partial=%s full_counter=%s saved=%s dt=%.2fs",
            len(entries),
            partial,
            cache.full_scan_counter,
            ok,
            time.monotonic() - t0,
        )
        return 0 if ok else 1
    except Exception as e:  # noqa: BLE001
        log.exception("scan_worker failed: %s", e)
        return 1
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    force = any(a in ("--full", "--force-full") for a in args)
    return run_scan_worker(force_full=force)


if __name__ == "__main__":
    # Dev: ensure repo root on path
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    raise SystemExit(main())
