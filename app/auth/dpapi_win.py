"""Windows DPAPI helpers (current-user scope).

Protects the DEK so CloneUp can decrypt the PAT without storing the master
password and without prompting on every GitHub operation.

Master password itself is never written to disk — only used in memory when
Settings creates/changes/removes protection.
"""

from __future__ import annotations

import sys
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    cast,
    create_string_buffer,
    windll,
)
from ctypes.wintypes import BOOL, DWORD, LPVOID


class _DATA_BLOB(Structure):
    _fields_ = [("cbData", DWORD), ("pbData", POINTER(c_char))]


class DpapiError(Exception):
    """DPAPI protect/unprotect failed."""


def dpapi_available() -> bool:
    return sys.platform == "win32"


def protect_bytes(data: bytes, *, entropy: bytes | None = None) -> bytes:
    """CryptProtectData — bound to current Windows user."""
    if not dpapi_available():
        raise DpapiError("DPAPI is only available on Windows")
    if not data:
        raise DpapiError("refusing to protect empty data")

    blob_in = _DATA_BLOB(
        len(data), cast(create_string_buffer(data, len(data)), POINTER(c_char))
    )
    blob_out = _DATA_BLOB()
    ent = None
    if entropy:
        ent = _DATA_BLOB(
            len(entropy),
            cast(create_string_buffer(entropy, len(entropy)), POINTER(c_char)),
        )

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1 — never show DPAPI UI
    ok = windll.crypt32.CryptProtectData(
        byref(blob_in),
        None,
        byref(ent) if ent is not None else None,
        None,
        None,
        0x1,
        byref(blob_out),
    )
    if not ok:
        raise DpapiError("CryptProtectData failed")
    try:
        return bytes(blob_out.pbData[: blob_out.cbData])
    finally:
        windll.kernel32.LocalFree(blob_out.pbData)


def unprotect_bytes(blob: bytes, *, entropy: bytes | None = None) -> bytes:
    """CryptUnprotectData — current Windows user only."""
    if not dpapi_available():
        raise DpapiError("DPAPI is only available on Windows")
    if not blob:
        raise DpapiError("empty DPAPI blob")

    blob_in = _DATA_BLOB(
        len(blob), cast(create_string_buffer(blob, len(blob)), POINTER(c_char))
    )
    blob_out = _DATA_BLOB()
    ent = None
    if entropy:
        ent = _DATA_BLOB(
            len(entropy),
            cast(create_string_buffer(entropy, len(entropy)), POINTER(c_char)),
        )

    ok = windll.crypt32.CryptUnprotectData(
        byref(blob_in),
        None,
        byref(ent) if ent is not None else None,
        None,
        None,
        0x1,
        byref(blob_out),
    )
    if not ok:
        raise DpapiError("CryptUnprotectData failed")
    try:
        return bytes(blob_out.pbData[: blob_out.cbData])
    finally:
        windll.kernel32.LocalFree(blob_out.pbData)
