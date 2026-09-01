"""
CloneUp_update_manager — silent loop.

  python -m update_manager
  CloneUp_update_manager.exe [--once] [--interval 600]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from update_manager import __version__
import tempfile
from pathlib import Path

from update_manager.apply import install_staged_onedir, stage_zip_update
from update_manager.config import INTERVAL_SEC
from update_manager.github_release import fetch_latest_release
from update_manager.logutil import setup_logging
from update_manager.paths import find_cloneup_install_dir
from update_manager.process_win import (
    is_tray_autostart_registered,
    kill_cloneup_processes,
    main_window_visible,
    restart_cloneup_tray,
)
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
    name = "Local\\CloneUpUpdateManagerMutex"
    handle = kernel32.CreateMutexW(None, False, name)
    last = kernel32.GetLastError()
    # ERROR_ALREADY_EXISTS = 183
    if last == 183:
        if handle:
            kernel32.CloseHandle(handle)
        return None
    return handle


def run_once(log: logging.Logger) -> str:
    """
    One update tick. Returns a short status token for tests/logs:
    no_install | no_version | no_release | up_to_date | deferred_ui | killed_failed | updated | error
    """
    install_dir = find_cloneup_install_dir()
    if install_dir is None:
        log.info("CloneUp install dir not found — skip")
        return "no_install"

    local = read_installed_version(install_dir)
    if local is None:
        log.warning("cannot read installed version under %s — skip", install_dir)
        return "no_version"

    release = fetch_latest_release()
    if release is None:
        log.info("no usable release / network — skip")
        return "no_release"

    if not is_newer(release.version, local):
        log.info(
            "up to date local=%s remote=%s",
            version_tuple_to_str(local),
            version_tuple_to_str(release.version),
        )
        return "up_to_date"

    log.info(
        "update available %s → %s (%s)",
        version_tuple_to_str(local),
        version_tuple_to_str(release.version),
        release.asset_name,
    )

    if main_window_visible():
        log.info("main window visible — defer update")
        return "deferred_ui"

    # Gap A: download + verify while CloneUp may still be running.
    # Only kill after the staged onedir is ready.
    try:
        with tempfile.TemporaryDirectory(prefix="cloneup_upd_") as tmp:
            src = stage_zip_update(release, Path(tmp))
            if main_window_visible():
                log.info("main window opened during download — defer apply")
                return "deferred_ui"
            if not kill_cloneup_processes():
                log.error("could not stop CloneUp.exe — abort update (files intact)")
                return "killed_failed"
            install_staged_onedir(src, install_dir)
    except Exception as e:
        log.exception("apply failed: %s", e)
        return "error"

    if is_tray_autostart_registered():
        restart_cloneup_tray(install_dir)

    log.info(
        "success %s → %s",
        version_tuple_to_str(local),
        version_tuple_to_str(release.version),
    )
    return "updated"


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

    mutex = _acquire_mutex()
    if mutex is None:
        log.warning("another update manager instance is running — exit")
        return 0

    try:
        if args.once:
            run_once(log)
            return 0
        # First tick soon after logon (disks/network), then every interval.
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
