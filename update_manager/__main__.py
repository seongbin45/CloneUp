"""
CloneUp_update_manager — silent loop.

  python -m update_manager
  CloneUp_update_manager.exe [--once] [--interval 600]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from update_manager import __version__
from update_manager.apply import install_staged_onedir
from update_manager.config import INTERVAL_SEC
from update_manager.github_release import fetch_latest_release
from update_manager.lock_win import PendingLock
from update_manager.logutil import setup_logging
from update_manager.paths import find_cloneup_install_dir, pending_version_dir
from update_manager.pending import (
    delete_version_dir,
    ensure_extract,
    ensure_zip,
    prune_other_versions,
    verify_zip_full,
)
from update_manager.process_win import (
    is_tray_autostart_registered,
    kill_cloneup_processes,
    main_window_visible,
    restart_cloneup_tray,
)
from update_manager import status_io
from update_manager.versioning import (
    is_newer,
    read_installed_version,
    version_tuple_to_str,
)


def _acquire_mutex():
    """Single instance via named mutex. Returns handle or None if already running."""
    if sys.platform != "win32":
        return object()
    import ctypes

    kernel32 = ctypes.windll.kernel32
    # Global so SYSTEM task and user tools coordinate better across sessions.
    name = "Global\\CloneUpUpdateManagerMutex"
    handle = kernel32.CreateMutexW(None, False, name)
    last = kernel32.GetLastError()
    if last == 183:
        if handle:
            kernel32.CloseHandle(handle)
        return None
    return handle


def _maybe_migrate_task(log: logging.Logger) -> None:
    """SYSTEM tick: ensure task is Parallel + runnable by users (best-effort)."""
    if sys.platform != "win32":
        return
    try:
        # Detect SYSTEM roughly: session 0 / no interactive USERNAME patterns
        # Migration is best-effort; failures are logged only.
        from update_manager.task_migrate import migrate_update_manager_task

        migrate_update_manager_task(log)
    except Exception as e:
        log.warning("task migrate skipped: %s", e)


def run_once(log: logging.Logger) -> str:
    """
    One update tick.

    Returns: no_install | no_version | no_release | up_to_date | deferred_ui
             | killed_failed | updated | error | pending_busy | pending_acl_failed
    """
    run_id = status_io.start_run(pid=os.getpid())
    try:
        try:
            status_io.ensure_status_acl()
        except Exception as e:
            log.warning("status ACL: %s", e)

        install_dir = find_cloneup_install_dir()
        if install_dir is None:
            log.info("CloneUp install dir not found — skip")
            status_io.finish_run(run_id, "no_install")
            return "no_install"

        local = read_installed_version(install_dir)
        if local is None:
            log.warning("cannot read installed version under %s — skip", install_dir)
            status_io.finish_run(run_id, "no_version")
            return "no_version"

        release = fetch_latest_release()
        if release is None:
            log.info("no usable release / network — skip")
            status_io.finish_run(run_id, "no_release")
            return "no_release"

        local_s = version_tuple_to_str(local)
        remote_s = version_tuple_to_str(release.version)
        status_io.update_run(run_id, local=local_s, remote=remote_s)

        if not is_newer(release.version, local):
            log.info("up to date local=%s remote=%s", local_s, remote_s)
            prune_other_versions(remote_s)
            status_io.finish_run(run_id, "up_to_date")
            return "up_to_date"

        log.info(
            "update available %s → %s (%s)",
            local_s,
            remote_s,
            release.asset_name,
        )

        pend = pending_version_dir(remote_s)
        lock = PendingLock(pend / "download.lock")
        if not lock.acquire():
            status_io.finish_run(run_id, "pending_busy")
            return "pending_busy"

        try:
            try:
                from update_manager.pending import ensure_pending_acl

                ensure_pending_acl(pend)
            except RuntimeError as e:
                log.error("%s", e)
                status_io.finish_run(run_id, "pending_acl_failed", error=str(e))
                return "pending_acl_failed"

            prune_other_versions(remote_s)
            status_io.update_run(run_id, phase="downloading")
            ensure_zip(pend, release)

            if main_window_visible():
                log.info("main window visible — defer apply (zip retained in pending)")
                status_io.finish_run(run_id, "deferred_ui")
                return "deferred_ui"

            # Apply gate — always re-hash
            verify_zip_full(pend, release)
            src = ensure_extract(pend, release)

            if main_window_visible():
                log.info("main window opened during extract — defer apply")
                status_io.finish_run(run_id, "deferred_ui")
                return "deferred_ui"

            if not kill_cloneup_processes():
                log.error("could not stop CloneUp.exe — abort update (files intact)")
                status_io.finish_run(run_id, "killed_failed")
                return "killed_failed"

            install_staged_onedir(src, install_dir)
            delete_version_dir(pend)

            if is_tray_autostart_registered():
                restart_cloneup_tray(install_dir)

            log.info("success %s → %s", local_s, remote_s)
            status_io.finish_run(run_id, "updated")
            return "updated"
        finally:
            lock.release()
    except Exception as e:
        log.exception("apply failed: %s", e)
        status_io.finish_run(run_id, "error", error=str(e))
        return "error"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check then exit (for tests)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=INTERVAL_SEC,
        help=f"Seconds between checks (default {INTERVAL_SEC})",
    )
    args = parser.parse_args(argv)

    log = setup_logging()
    log.info("CloneUp Update Manager %s starting", __version__)
    _maybe_migrate_task(log)

    mutex = _acquire_mutex()
    if mutex is None:
        # Daemon already holds Global mutex. Parallel / schtasks /Run still
        # gets a one-shot tick (PendingLock serializes downloads; per-run
        # status preserves identity). Do not become a second long-runner.
        log.info("daemon mutex held — Parallel one-shot tick")
        run_once(log)
        return 0

    try:
        if args.once:
            run_once(log)
            return 0
        time.sleep(min(30, max(5, args.interval // 20)))
        while True:
            try:
                run_once(log)
            except Exception:
                log.exception("tick crashed")
            time.sleep(max(60, int(args.interval)))
    finally:
        if sys.platform == "win32" and mutex is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(mutex)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
