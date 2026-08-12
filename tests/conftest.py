"""CI / headless defaults — must run before any PySide6 or keyring import.

Without QT_QPA_PLATFORM=offscreen, QApplication + show()/winId() can block
forever on GitHub Actions windows-latest (looks like a stuck workflow).
"""

from __future__ import annotations

import os

# Before PySide6 is imported by any test module.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Avoid Windows Credential Manager prompts / hangs on GHA runners.
os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
