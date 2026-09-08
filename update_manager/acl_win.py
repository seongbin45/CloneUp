"""Windows ACL helpers for pending/status trees (Tier 2)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("cloneup_update_manager")


def ensure_dir_acl(path: Path, *, mode: str) -> None:
    """
    Apply Tier-2 ACL. Raises RuntimeError on failure (hard-fail tick).

    machine: SYSTEM + Administrators Modify (no Users write)
    user: grant current user Modify via icacls %USERNAME%
    status machine: additionally Users Read
    """
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        return
    # Reset inheritance then grant required principals.
    cmds: list[list[str]] = [
        ["icacls", str(path), "/inheritance:r"],
    ]
    if mode == "machine":
        cmds.append(
            [
                "icacls",
                str(path),
                "/grant",
                "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
                "BUILTIN\\Administrators:(OI)(CI)M",
            ]
        )
    elif mode == "machine_status":
        cmds.append(
            [
                "icacls",
                str(path),
                "/grant",
                "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
                "BUILTIN\\Administrators:(OI)(CI)M",
                "BUILTIN\\Users:(OI)(CI)R",
            ]
        )
    else:
        # user mode — grant current user full modify on the tree
        import os

        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if not user:
            raise RuntimeError("cannot determine USERNAME for pending ACL")
        cmds.append(
            [
                "icacls",
                str(path),
                "/grant",
                f"{user}:(OI)(CI)M",
                "NT AUTHORITY\\SYSTEM:(OI)(CI)M",
            ]
        )
    for cmd in cmds:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            log.error("icacls failed (%s): %s", " ".join(cmd[2:4]), err)
            raise RuntimeError(f"pending_acl_failed: {err[:200]}")
