"""Environment for non-interactive git (never hang waiting for credentials)."""

from __future__ import annotations

import os
from typing import Mapping


def noninteractive_git_env(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """
    Env for every git subprocess.

    - GIT_TERMINAL_PROMPT=0: git will not prompt; fails instead of hanging
    - GCM_INTERACTIVE=Never: Git Credential Manager must not open UI
    """
    env = dict(base if base is not None else os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    # Extra belt-and-suspenders on some GCM builds
    env.setdefault("GIT_ASKPASS", "")
    env.setdefault("GCM_CREDENTIAL_STORE", "")
    return env
