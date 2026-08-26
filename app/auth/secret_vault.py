"""Master-password vault layout + DPAPI DEK for day-to-day unlock (Phase 2).

On-disk (never stores the master password)::

    %LOCALAPPDATA%\\CloneUp\\secret\\
      wrap.json   — WrappedDek (Settings enable / change / verify)
      dek.dpapi   — DEK sealed with Windows DPAPI (current user)

Keyring holds either a plaintext PAT (legacy / unprotected) or
``enc.v1.<urlsafe-b64>`` ciphertext when protection is on.

Master password is used only in memory for enable / change / disable.
Daily ``load_token`` unwraps the DEK via DPAPI — no password prompt.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .dpapi_win import DpapiError, dpapi_available, protect_bytes, unprotect_bytes
from .secret_crypto import (
    DEK_LEN,
    AuthenticationError,
    CryptoError,
    WrappedDek,
    decrypt_token,
    encrypt_token,
    generate_dek,
    unwrap_dek_with_password,
    verify_password,
    wrap_dek_with_password,
)

logger = logging.getLogger(__name__)

WRAP_FILENAME = "wrap.json"
DEK_DPAPI_FILENAME = "dek.dpapi"
# Keyring wire prefix for encrypted PATs (versioned).
TOKEN_ENC_PREFIX = "enc.v1."

# Optional DPAPI entropy so a stolen dek.dpapi blob is not reusable as-is
# with a generic CryptUnprotectData call from another CloneUp context.
_DPAPI_ENTROPY = b"CloneUp-dek-dpapi-v1"


class VaultError(Exception):
    """Vault / protection configuration failure."""


class VaultLockedError(VaultError):
    """DPAPI unwrap failed (wrong Windows user, corrupted blob, etc.)."""


def secret_dir(*, create: bool = False) -> Path:
    """``%LOCALAPPDATA%\\CloneUp\\secret`` (falls back to TMP)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or tempfile.gettempdir()
    d = Path(base) / "CloneUp" / "secret"
    if create:
        d.mkdir(parents=True, exist_ok=True)
        _harden_acl(d)
    return d


def wrap_path() -> Path:
    return secret_dir() / WRAP_FILENAME


def dek_dpapi_path() -> Path:
    return secret_dir() / DEK_DPAPI_FILENAME


def is_protection_enabled() -> bool:
    """True when both wrap.json and dek.dpapi are present."""
    return wrap_path().is_file() and dek_dpapi_path().is_file()


def is_encrypted_blob(raw: str | None) -> bool:
    """True when keyring value looks like an ``enc.v1.`` ciphertext."""
    if not raw:
        return False
    return raw.startswith(TOKEN_ENC_PREFIX)


def encode_cipher_for_keyring(cipher: bytes) -> str:
    if not cipher:
        raise VaultError("refusing to encode empty ciphertext")
    return TOKEN_ENC_PREFIX + base64.urlsafe_b64encode(cipher).decode("ascii")


def decode_cipher_from_keyring(raw: str) -> bytes:
    if not is_encrypted_blob(raw):
        raise VaultError("not an encrypted token blob")
    b64 = raw[len(TOKEN_ENC_PREFIX) :]
    try:
        return base64.urlsafe_b64decode(b64.encode("ascii"))
    except (ValueError, TypeError) as e:
        raise VaultError("invalid enc.v1 ciphertext encoding") from e


def load_wrapped_dek() -> WrappedDek | None:
    path = wrap_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise VaultError(f"cannot read wrap.json: {e}") from e
    try:
        return WrappedDek.from_dict(data)
    except CryptoError as e:
        raise VaultError(f"invalid wrap.json: {e}") from e


def load_dek() -> bytes:
    """
    Recover DEK via DPAPI for day-to-day use.

    Does **not** need the master password. Wrong Windows user / corrupted
    blob → ``VaultLockedError``.
    """
    if not dpapi_available():
        raise VaultError("DPAPI unavailable — master protection requires Windows")
    path = dek_dpapi_path()
    if not path.is_file():
        raise VaultError("master protection not enabled (missing dek.dpapi)")
    try:
        blob = path.read_bytes()
    except OSError as e:
        raise VaultError(f"cannot read dek.dpapi: {e}") from e
    try:
        dek = unprotect_bytes(blob, entropy=_DPAPI_ENTROPY)
    except DpapiError as e:
        raise VaultLockedError(
            "cannot unlock DEK with DPAPI (wrong Windows user or corrupted vault)"
        ) from e
    if len(dek) != DEK_LEN:
        raise VaultLockedError("DPAPI returned invalid DEK length")
    return dek


def encrypt_token_for_store(token: str, *, dek: bytes | None = None) -> str:
    """Return ``enc.v1.…`` string suitable for keyring storage."""
    key = dek if dek is not None else load_dek()
    try:
        cipher = encrypt_token(token.strip(), key)
    except CryptoError as e:
        raise VaultError(str(e)) from e
    return encode_cipher_for_keyring(cipher)


def decrypt_token_from_store(raw: str, *, dek: bytes | None = None) -> str:
    """Decrypt an ``enc.v1.…`` keyring value to the plaintext PAT."""
    key = dek if dek is not None else load_dek()
    cipher = decode_cipher_from_keyring(raw)
    try:
        return decrypt_token(cipher, key)
    except AuthenticationError as e:
        raise VaultLockedError("token decrypt failed (wrong DEK or tampered data)") from e
    except CryptoError as e:
        raise VaultError(str(e)) from e


def enable_protection(password: str, *, plaintext_token: str | None = None) -> str | None:
    """
    Turn on master protection.

    - Creates a fresh DEK, wraps it with ``password``, seals a DPAPI copy.
    - If ``plaintext_token`` is given, returns the ``enc.v1.…`` blob to store
      in keyring (caller writes it). If protection was already on, raises.

    Master password is never written to disk.
    """
    if is_protection_enabled():
        raise VaultError("master protection is already enabled")
    if not dpapi_available():
        raise VaultError("DPAPI unavailable — master protection requires Windows")
    pw = password or ""
    if not pw.strip():
        raise VaultError("empty master password not allowed")

    dek = generate_dek()
    wrapped = wrap_dek_with_password(dek, pw)
    try:
        dpapi_blob = protect_bytes(dek, entropy=_DPAPI_ENTROPY)
    except DpapiError as e:
        raise VaultError(f"DPAPI protect failed: {e}") from e

    d = secret_dir(create=True)
    wrap_file = d / WRAP_FILENAME
    dek_file = d / DEK_DPAPI_FILENAME
    # Write wrap first, then DPAPI blob; on failure clean both.
    try:
        _atomic_write_text(wrap_file, json.dumps(wrapped.to_dict(), indent=2) + "\n")
        _atomic_write_bytes(dek_file, dpapi_blob)
        _harden_acl(d)
    except OSError as e:
        _best_effort_unlink(wrap_file)
        _best_effort_unlink(dek_file)
        raise VaultError(f"cannot write vault files: {e}") from e

    if plaintext_token is None:
        return None
    token = plaintext_token.strip()
    if not token:
        raise VaultError("refusing to encrypt empty token")
    return encrypt_token_for_store(token, dek=dek)


def change_password(old_password: str, new_password: str) -> None:
    """Re-wrap DEK with a new master password. DPAPI blob unchanged."""
    if not is_protection_enabled():
        raise VaultError("master protection is not enabled")
    if not (new_password or "").strip():
        raise VaultError("empty master password not allowed")
    w = load_wrapped_dek()
    if w is None:
        raise VaultError("missing wrap.json")
    try:
        dek = unwrap_dek_with_password(w, old_password)
    except AuthenticationError as e:
        raise VaultError("wrong current master password") from e
    new_wrap = wrap_dek_with_password(dek, new_password)
    try:
        _atomic_write_text(
            wrap_path(), json.dumps(new_wrap.to_dict(), indent=2) + "\n"
        )
    except OSError as e:
        raise VaultError(f"cannot update wrap.json: {e}") from e


def disable_protection(password: str, *, encrypted_blob: str | None = None) -> str | None:
    """
    Turn off master protection after verifying ``password``.

    If ``encrypted_blob`` is an ``enc.v1.…`` value, returns the plaintext PAT
    so the caller can rewrite keyring. Vault files are removed on success.
    """
    if not is_protection_enabled():
        raise VaultError("master protection is not enabled")
    w = load_wrapped_dek()
    if w is None:
        raise VaultError("missing wrap.json")
    try:
        dek = unwrap_dek_with_password(w, password)
    except AuthenticationError as e:
        raise VaultError("wrong master password") from e

    plaintext: str | None = None
    if encrypted_blob is not None and is_encrypted_blob(encrypted_blob):
        plaintext = decrypt_token_from_store(encrypted_blob, dek=dek)

    clear_vault()
    return plaintext


def verify_master_password(password: str) -> bool:
    """True if ``password`` matches the stored verifier."""
    w = load_wrapped_dek()
    if w is None:
        return False
    return verify_password(w, password)


def clear_vault() -> None:
    """Delete wrap.json and dek.dpapi (best-effort). Does not touch keyring."""
    _best_effort_unlink(wrap_path())
    _best_effort_unlink(dek_dpapi_path())
    # Leave the directory; empty dir is fine.


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        _best_effort_unlink(tmp)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _best_effort_unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _harden_acl(directory: Path) -> None:
    """
    Best-effort: restrict ``directory`` to the current Windows user.

    Uses ``icacls``. Failure is logged but not fatal — DPAPI remains the
    primary protection for the DEK.
    """
    if os.name != "nt":
        return
    try:
        user = os.environ.get("USERNAME") or os.getlogin()
    except OSError:
        user = None
    if not user:
        return
    try:
        # Reset inherited ACLs, grant current user full control only.
        # encoding=locale-safe: icacls on Korean Windows emits CP949, not UTF-8.
        subprocess.run(
            [
                "icacls",
                str(directory),
                "/inheritance:r",
                "/grant:r",
                f"{user}:(OI)(CI)F",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("icacls harden failed for %s: %s", directory, e)
