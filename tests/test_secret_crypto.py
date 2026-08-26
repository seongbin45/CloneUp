"""Phase 1: master-password crypto unit tests (no UI / keyring)."""

from __future__ import annotations

import base64
import unicodedata

import pytest

from app.auth.secret_crypto import (
    FORMAT_VERSION,
    KDF_ITERATIONS,
    KDF_ITERATIONS_MAX,
    KDF_ITERATIONS_MIN,
    SALT_LEN,
    VERIFIER_LEN,
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


def test_encrypt_decrypt_roundtrip() -> None:
    dek = generate_dek()
    assert len(dek) == 32
    token = "ghp_" + ("Z" * 36)
    blob = encrypt_token(token, dek)
    assert isinstance(blob, (bytes, bytearray))
    assert blob != token.encode("utf-8")
    assert decrypt_token(blob, dek) == token


def test_decrypt_rejects_tamper() -> None:
    dek = generate_dek()
    blob = bytearray(encrypt_token("ghp_" + ("a" * 36), dek))
    blob[-1] ^= 0xFF
    with pytest.raises(AuthenticationError):
        decrypt_token(bytes(blob), dek)


def test_decrypt_rejects_wrong_dek() -> None:
    blob = encrypt_token("ghp_" + ("b" * 36), generate_dek())
    with pytest.raises(AuthenticationError):
        decrypt_token(blob, generate_dek())


def test_decrypt_rejects_short_blob() -> None:
    with pytest.raises(AuthenticationError):
        decrypt_token(b"short", generate_dek())


def test_wrap_unwrap_roundtrip() -> None:
    dek = generate_dek()
    w = wrap_dek_with_password(dek, "correct horse battery")
    assert verify_password(w, "correct horse battery")
    assert not verify_password(w, "wrong password")
    assert unwrap_dek_with_password(w, "correct horse battery") == dek


def test_unwrap_rejects_wrong_password() -> None:
    dek = generate_dek()
    w = wrap_dek_with_password(dek, "secret-master")
    with pytest.raises(AuthenticationError):
        unwrap_dek_with_password(w, "nope")


def test_unwrap_rejects_tampered_wrapped_with_correct_password() -> None:
    dek = generate_dek()
    w = wrap_dek_with_password(dek, "secret-master")
    tampered = bytearray(w.wrapped)
    tampered[-1] ^= 0x01
    w2 = WrappedDek(
        salt=w.salt,
        wrapped=bytes(tampered),
        verifier=w.verifier,
        kdf=w.kdf,
        iterations=w.iterations,
    )
    with pytest.raises(AuthenticationError):
        unwrap_dek_with_password(w2, "secret-master")


def test_wrapped_dek_dict_roundtrip() -> None:
    dek = generate_dek()
    w = wrap_dek_with_password(dek, "pw-ä-한글")
    w2 = WrappedDek.from_dict(w.to_dict())
    assert unwrap_dek_with_password(w2, "pw-ä-한글") == dek
    assert verify_password(w2, "pw-ä-한글")
    assert w.to_dict()["v"] == FORMAT_VERSION


def test_empty_and_whitespace_password_rejected() -> None:
    dek = generate_dek()
    with pytest.raises((AuthenticationError, CryptoError)):
        wrap_dek_with_password(dek, "")
    with pytest.raises((AuthenticationError, CryptoError)):
        wrap_dek_with_password(dek, "   ")
    with pytest.raises((AuthenticationError, CryptoError)):
        wrap_dek_with_password(dek, "\t\n")


def test_unwrap_empty_password_is_authentication_error() -> None:
    dek = generate_dek()
    w = wrap_dek_with_password(dek, "ok-password")
    with pytest.raises(AuthenticationError):
        unwrap_dek_with_password(w, "")
    assert verify_password(w, "") is False
    assert verify_password(w, "   ") is False


def test_encrypt_empty_or_padded_token_rejected() -> None:
    dek = generate_dek()
    with pytest.raises(CryptoError):
        encrypt_token("   ", dek)
    with pytest.raises(CryptoError):
        encrypt_token("  ghp_xxx  ", dek)


def test_from_dict_rejects_low_iterations() -> None:
    w = wrap_dek_with_password(generate_dek(), "pw")
    d = w.to_dict()
    d["iterations"] = 1
    with pytest.raises(CryptoError, match="iterations"):
        WrappedDek.from_dict(d)


def test_from_dict_rejects_huge_iterations() -> None:
    w = wrap_dek_with_password(generate_dek(), "pw")
    d = w.to_dict()
    d["iterations"] = KDF_ITERATIONS_MAX + 1
    with pytest.raises(CryptoError, match="iterations"):
        WrappedDek.from_dict(d)


def test_from_dict_accepts_min_iterations() -> None:
    w = wrap_dek_with_password(generate_dek(), "pw")
    d = w.to_dict()
    d["iterations"] = KDF_ITERATIONS_MIN
    # Re-wrap would use KDF_ITERATIONS; here we only validate struct load
    # with same verifier won't unwrap unless iterations match wrap — just
    # ensure from_dict accepts the floor value.
    w2 = WrappedDek.from_dict(d)
    assert w2.iterations == KDF_ITERATIONS_MIN


def test_from_dict_rejects_bad_lengths_and_version() -> None:
    w = wrap_dek_with_password(generate_dek(), "pw")
    d = w.to_dict()

    bad_salt = dict(d)
    bad_salt["salt"] = base64.urlsafe_b64encode(b"short").decode("ascii")
    with pytest.raises(CryptoError, match="salt"):
        WrappedDek.from_dict(bad_salt)

    bad_ver = dict(d)
    bad_ver["verifier"] = base64.urlsafe_b64encode(b"x" * 8).decode("ascii")
    with pytest.raises(CryptoError, match="verifier"):
        WrappedDek.from_dict(bad_ver)

    bad_wrap = dict(d)
    bad_wrap["wrapped"] = base64.urlsafe_b64encode(b"x" * 8).decode("ascii")
    with pytest.raises(CryptoError, match="wrapped"):
        WrappedDek.from_dict(bad_wrap)

    bad_v = dict(d)
    bad_v["v"] = 99
    with pytest.raises(CryptoError, match="version"):
        WrappedDek.from_dict(bad_v)

    bad_kdf = dict(d)
    bad_kdf["kdf"] = "argon2id"
    with pytest.raises(CryptoError, match="kdf"):
        WrappedDek.from_dict(bad_kdf)


def test_verify_rejects_wrong_kdf_on_object() -> None:
    w = wrap_dek_with_password(generate_dek(), "pw")
    w_bad = WrappedDek(
        salt=w.salt,
        wrapped=w.wrapped,
        verifier=w.verifier,
        kdf="argon2id",
        iterations=w.iterations,
    )
    assert verify_password(w_bad, "pw") is False
    with pytest.raises(CryptoError):
        unwrap_dek_with_password(w_bad, "pw")


def test_unicode_nfc_nfd_same_password() -> None:
    # é as composed (NFC) vs e + combining acute (NFD)
    nfc = unicodedata.normalize("NFC", "cafe\u0301")
    nfd = unicodedata.normalize("NFD", "cafe\u0301")
    assert nfc != nfd  # raw strings differ
    dek = generate_dek()
    w = wrap_dek_with_password(dek, nfc)
    assert verify_password(w, nfd)
    assert unwrap_dek_with_password(w, nfd) == dek


def test_bad_dek_length_rejected() -> None:
    with pytest.raises(CryptoError):
        encrypt_token("ghp_" + ("c" * 36), b"short")
    with pytest.raises(CryptoError):
        wrap_dek_with_password(b"\x00" * 16, "pw")


def test_full_pipeline_master_protects_token() -> None:
    """Settings-set master → wrap DEK → encrypt PAT → wrong pw cannot recover."""
    password = "CloneUp-Master-Test-1"
    token = "github_pat_" + ("x" * 40)
    dek = generate_dek()
    wrapped = wrap_dek_with_password(dek, password)
    cipher = encrypt_token(token, dek)

    payload = {
        "cipher": cipher.hex(),
        "wrap": wrapped.to_dict(),
    }

    w2 = WrappedDek.from_dict(payload["wrap"])
    assert verify_password(w2, password)
    dek2 = unwrap_dek_with_password(w2, password)
    assert decrypt_token(bytes.fromhex(payload["cipher"]), dek2) == token

    with pytest.raises(AuthenticationError):
        unwrap_dek_with_password(w2, "CloneUp-Master-Test-2")
