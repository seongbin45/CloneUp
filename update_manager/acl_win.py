"""Windows ACL helpers for pending/status trees (Tier 2)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("cloneup_update_manager")


def acl_grant_args(mode: str) -> list[str]:
    """icacls ``/grant`` principals for *mode* (unit-testable without icacls)."""
    if mode == "machine":
        # Pending zip: no Users write.
        return [
            "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
            "BUILTIN\\Administrators:(OI)(CI)M",
        ]
    if mode == "machine_status":
        # Status/runs: Users need Modify. Tray or HKCU Run may start UM as the
        # interactive user; Read-only caused PermissionError on ``*.tmp``
        # (GitHub auto-issues #4–#10, Errno 13).
        return [
            "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
            "BUILTIN\\Administrators:(OI)(CI)M",
            "BUILTIN\\Users:(OI)(CI)M",
        ]
    # user mode — grant current user Modify
    import os

    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        raise RuntimeError("cannot determine USERNAME for pending ACL")
    return [
        f"{user}:(OI)(CI)M",
        "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
    ]


def ensure_dir_acl(path: Path, *, mode: str) -> None:
    """
    Apply Tier-2 ACL. Raises RuntimeError on failure (hard-fail tick).

    machine: SYSTEM + Administrators Modify (pending zip; no Users write)
    machine_status: SYSTEM + Admins + Users Modify (status JSON writable)
    user: current user + SYSTEM Modify
    """
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        return
    cmds: list[list[str]] = [
        ["icacls", str(path), "/inheritance:r"],
        ["icacls", str(path), "/grant", *acl_grant_args(mode)],
    ]
    # Hide console: windowed UM still flashes a black terminal per icacls without this.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
    for cmd in cmds:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=flags,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.error("icacls failed (%s): %s", " ".join(cmd[2:4]), err)
            raise RuntimeError(f"pending_acl_failed: {err[:200]}")
