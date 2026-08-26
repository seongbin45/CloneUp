"""Master-password cryptography for CloneUp secrets (Phase 1).

Pure crypto helpers — no keyring, no UI, no DPAPI.

- DEK (32 bytes): encrypts the GitHub PAT with AES-GCM
- KEK: derived from master password via PBKDF2-HMAC-SHA256
- WrappedDek: DEK wrapped for Settings create/change/verify

Day-to-day ``load_token`` unwraps DEK via Windows DPAPI (see ``secret_vault``);
this module only handles password-based wrap/unwrap and token encrypt/decrypt.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- parameters (bump ``FORMAT_VERSION`` if changed incompatibly) ---
FORMAT_VERSION = 1
KDF_NAME = "pbkdf2-sha256"
KDF_ITERATIONS = 600_000
KDF_ITERATIONS_MIN = 600_000
KDF_ITERATIONS_MAX = 5_000_000
SALT_LEN = 16
DEK_LEN = 32
NONCE_LEN = 12
# AES-GCM tag is 16 bytes; wrapped body = nonce || enc(DEK) || tag
WRAPPED_MIN_LEN = NONCE_LEN + DEK_LEN + 16
VERIFIER_LEN = 32  # HMAC-SHA256
PASSWORD_MAX_LEN = 1024
TOKEN_AAD = b"CloneUp-pat-v1"
VERIFIER_INFO = b"CloneUp-master-verifier-v1"
WRAP_INFO = b"CloneUp-dek-wrap-v1"


class CryptoError(Exception):
    """Base error for secret crypto failures."""


class AuthenticationError(CryptoError):
    """Wrong password, tampered blob, or AEAD failure."""


@dataclass(frozen=True)
class WrappedDek:
    """DEK protected by a master password (for Settings only)."""

    salt: bytes
    wrapped: bytes
    verifier: bytes
    kdf: str = KDF_NAME
    iterations: int = KDF_ITERATIONS

    def to_dict(self) -> dict:
        import base64

        b64 = base64.urlsafe_b64encode
        return {
            "salt": b64(self.salt).decode("ascii"),
            "wrapped": b64(self.wrapped).decode("ascii"),
            "verifier": b64(self.verifier).decode("ascii"),
            "kdf": self.kdf,
            "iterations": int(self.iterations),
            "v": FORMAT_VERSION,
        }

    @staticmethod
    def from_dict(data: dict) -> "WrappedDek":
        import base64

        if not isinstance(data, dict):
            raise CryptoError("invalid WrappedDek payload: not a dict")
        try:
            ver = int(data.get("v", FORMAT_VERSION))
        except (TypeError, ValueError) as e:
            raise CryptoError("invalid WrappedDek version") from e
        if ver != FORMAT_VERSION:
            raise CryptoError(f"unsupported WrappedDek version: {ver}")

        b64 = base64.urlsafe_b64decode
        try:
            salt = b64(str(data["salt"]).encode("ascii"))
            wrapped = b64(str(data["wrapped"]).encode("ascii"))
            verifier = b64(str(data["verifier"]).encode("ascii"))
            kdf = str(data.get("kdf") or KDF_NAME)
            iterations = int(data["iterations"]) if "iterations" in data else KDF_ITERATIONS
        except (KeyError, ValueError, TypeError) as e:
            raise CryptoError(f"invalid WrappedDek payload: {e}") from e

        if kdf != KDF_NAME:
            raise CryptoError(f"unsupported kdf: {kdf}")
        if not (KDF_ITERATIONS_MIN <= iterations <= KDF_ITERATIONS_MAX):
            raise CryptoError(
                f"iterations out of range "
                f"[{KDF_ITERATIONS_MIN}, {KDF_ITERATIONS_MAX}]: {iterations}"
            )
        if len(salt) != SALT_LEN:
            raise CryptoError(f"salt must be {SALT_LEN} bytes")
        if len(verifier) != VERIFIER_LEN:
            raise CryptoError(f"verifier must be {VERIFIER_LEN} bytes")
        if len(wrapped) < WRAPPED_MIN_LEN:
            raise CryptoError("wrapped DEK too short")

        return WrappedDek(
            salt=salt,
            wrapped=wrapped,
            verifier=verifier,
            kdf=kdf,
            iterations=iterations,
        )


def generate_dek() -> bytes:
    """Fresh 256-bit data-encryption key."""
    return secrets.token_bytes(DEK_LEN)


def _normalize_password(password: str) -> str:
    if not isinstance(password, str):
        raise TypeError("password must be str")
    # NFKC: stable across IME / composed vs decomposed characters
    return unicodedata.normalize("NFKC", password)


def _kdf(password: str, salt: bytes, *, iterations: int = KDF_ITERATIONS) -> bytes:
    pw = _normalize_password(password)
    if not pw or not pw.strip():
        raise AuthenticationError("empty password not allowed")
    if len(pw) > PASSWORD_MAX_LEN:
        raise CryptoError(f"password longer than {PASSWORD_MAX_LEN} characters")
    if not salt or len(salt) < 8:
        raise CryptoError("salt too short")
    iters = int(iterations)
    if not (KDF_ITERATIONS_MIN <= iters <= KDF_ITERATIONS_MAX):
        raise CryptoError("iterations out of range")
    return hashlib.pbkdf2_hmac(
        "sha256",
        pw.encode("utf-8"),
        salt,
        iters,
        dklen=DEK_LEN,
    )


def _hkdf_like(key: bytes, info: bytes) -> bytes:
    """Simple one-shot HMAC expand (labeled subkeys from high-entropy KEK)."""
    return hmac.new(key, info, hashlib.sha256).digest()


def encrypt_token(token: str, dek: bytes) -> bytes:
    """
    AES-GCM seal. Wire format: ``nonce (12) || ciphertext+tag``.

    AAD binds ciphertext to PAT purpose (``TOKEN_AAD``).
    """
    if not isinstance(token, str):
        raise TypeError("token must be str")
    stripped = token.strip()
    if not stripped:
        raise CryptoError("refusing to encrypt empty token")
    if stripped != token:
        raise CryptoError("token must not have leading/trailing whitespace")
    if not isinstance(dek, (bytes, bytearray)) or len(dek) != DEK_LEN:
        raise CryptoError("DEK must be 32 bytes")
    nonce = secrets.token_bytes(NONCE_LEN)
    aes = AESGCM(bytes(dek))
    ct = aes.encrypt(nonce, stripped.encode("utf-8"), TOKEN_AAD)
    return nonce + ct


def decrypt_token(blob: bytes, dek: bytes) -> str:
    """Inverse of ``encrypt_token``. Tampering → ``AuthenticationError``."""
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < NONCE_LEN + 16:
        raise AuthenticationError("ciphertext too short")
    if not isinstance(dek, (bytes, bytearray)) or len(dek) != DEK_LEN:
        raise CryptoError("DEK must be 32 bytes")
    nonce = bytes(blob[:NONCE_LEN])
    ct = bytes(blob[NONCE_LEN:])
    aes = AESGCM(bytes(dek))
    try:
        pt = aes.decrypt(nonce, ct, TOKEN_AAD)
    except InvalidTag as e:
        raise AuthenticationError("decrypt failed (wrong key or tampered data)") from e
    return pt.decode("utf-8")


def wrap_dek_with_password(dek: bytes, password: str) -> WrappedDek:
    """Protect DEK with master password; also store a password verifier."""
    if not isinstance(dek, (bytes, bytearray)) or len(dek) != DEK_LEN:
        raise CryptoError("DEK must be 32 bytes")
    salt = secrets.token_bytes(SALT_LEN)
    kek = _kdf(password, salt)
    wrap_key = _hkdf_like(kek, WRAP_INFO)
    nonce = secrets.token_bytes(NONCE_LEN)
    wrapped_body = AESGCM(wrap_key).encrypt(nonce, bytes(dek), WRAP_INFO)
    wrapped = nonce + wrapped_body
    verifier = _hkdf_like(kek, VERIFIER_INFO)
    return WrappedDek(
        salt=salt,
        wrapped=wrapped,
        verifier=verifier,
        kdf=KDF_NAME,
        iterations=KDF_ITERATIONS,
    )


def unwrap_dek_with_password(w: WrappedDek, password: str) -> bytes:
    """Recover DEK; wrong password or tamper → ``AuthenticationError``."""
    if w.kdf != KDF_NAME:
        raise CryptoError(f"unsupported kdf: {w.kdf}")
    if len(w.verifier) != VERIFIER_LEN:
        raise AuthenticationError("invalid verifier")
    if len(w.wrapped) < WRAPPED_MIN_LEN:
        raise AuthenticationError("wrapped DEK too short")
    try:
        kek = _kdf(password, w.salt, iterations=w.iterations)
    except AuthenticationError:
        raise
    except CryptoError as e:
        raise AuthenticationError(str(e)) from e
    expected = _hkdf_like(kek, VERIFIER_INFO)
    if not hmac.compare_digest(w.verifier, expected):
        raise AuthenticationError("wrong master password")
    wrap_key = _hkdf_like(kek, WRAP_INFO)
    nonce = w.wrapped[:NONCE_LEN]
    body = w.wrapped[NONCE_LEN:]
    try:
        dek = AESGCM(wrap_key).decrypt(nonce, body, WRAP_INFO)
    except InvalidTag as e:
        raise AuthenticationError("unwrap failed") from e
    if len(dek) != DEK_LEN:
        raise AuthenticationError("invalid DEK length after unwrap")
    return dek


def verify_password(w: WrappedDek, password: str) -> bool:
    """True if ``password`` matches the verifier (constant-time compare)."""
    if w.kdf != KDF_NAME:
        return False
    if len(w.verifier) != VERIFIER_LEN:
        return False
    try:
        kek = _kdf(password, w.salt, iterations=w.iterations)
    except (AuthenticationError, CryptoError):
        return False
    expected = _hkdf_like(kek, VERIFIER_INFO)
    return hmac.compare_digest(w.verifier, expected)
