"""Phase 2: secret vault + DPAPI DEK + token_store encryption path."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.auth.dpapi_win import dpapi_available
from app.auth.secret_crypto import DEK_LEN, generate_dek
from app.auth.secret_vault import (
    TOKEN_ENC_PREFIX,
    VaultError,
    VaultLockedError,
    change_password,
    clear_vault,
    decode_cipher_from_keyring,
    decrypt_token_from_store,
    disable_protection,
    enable_protection,
    encode_cipher_for_keyring,
    encrypt_token_for_store,
    is_encrypted_blob,
    is_protection_enabled,
    load_dek,
    load_wrapped_dek,
    verify_master_password,
)
from app.auth.token_store import (
    change_master_password,
    delete_token,
    disable_master_protection,
    enable_master_protection,
    is_token_encrypted,
    load_token,
    load_token_raw,
    master_protection_enabled,
    save_token,
)

_WIN = sys.platform == "win32" and dpapi_available()


@pytest.fixture()
def vault_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point vault at a temp LOCALAPPDATA and clear between tests."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    clear_vault()
    yield tmp_path
    clear_vault()


def _fake_keyring():
    store: dict[str, str] = {}

    def _set(service: str, user: str, password: str) -> None:
        assert service == "CloneUp"
        store[user] = password

    def _get(service: str, user: str) -> str | None:
        return store.get(user)

    def _delete(service: str, user: str) -> None:
        store.pop(user, None)

    return store, _set, _get, _delete


# --- blob encoding -----------------------------------------------------------


def test_enc_v1_roundtrip_encoding() -> None:
    raw = b"\x00\x01\xff" + b"cipher"
    s = encode_cipher_for_keyring(raw)
    assert s.startswith(TOKEN_ENC_PREFIX)
    assert is_encrypted_blob(s)
    assert decode_cipher_from_keyring(s) == raw
    assert not is_encrypted_blob("ghp_plaintext")
    assert not is_encrypted_blob(None)


def test_encode_rejects_empty() -> None:
    with pytest.raises(VaultError):
        encode_cipher_for_keyring(b"")


# --- enable / load / disable (real DPAPI on Windows) -------------------------


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_enable_load_disable_roundtrip(vault_tmpdir: Path) -> None:
    password = "CloneUp-Vault-Test-1"
    token = "ghp_" + ("v" * 36)

    enc = enable_protection(password, plaintext_token=token)
    assert enc is not None
    assert is_encrypted_blob(enc)
    assert is_protection_enabled()
    assert (vault_tmpdir / "CloneUp" / "secret" / "wrap.json").is_file()
    assert (vault_tmpdir / "CloneUp" / "secret" / "dek.dpapi").is_file()

    dek = load_dek()
    assert len(dek) == DEK_LEN
    assert decrypt_token_from_store(enc, dek=dek) == token
    assert verify_master_password(password)
    assert not verify_master_password("wrong-password")

    plain = disable_protection(password, encrypted_blob=enc)
    assert plain == token
    assert not is_protection_enabled()


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_enable_rejects_empty_password(vault_tmpdir: Path) -> None:
    with pytest.raises(VaultError):
        enable_protection("   ")
    assert not is_protection_enabled()


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_enable_twice_fails(vault_tmpdir: Path) -> None:
    enable_protection("pw-one-long-enough")
    with pytest.raises(VaultError, match="already enabled"):
        enable_protection("pw-two-long-enough")


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_change_password(vault_tmpdir: Path) -> None:
    enable_protection("old-master-pw")
    change_password("old-master-pw", "new-master-pw")
    assert verify_master_password("new-master-pw")
    assert not verify_master_password("old-master-pw")
    # DPAPI path still unlocks without password
    assert len(load_dek()) == DEK_LEN


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_wrong_password_on_disable(vault_tmpdir: Path) -> None:
    enable_protection("correct-pw")
    with pytest.raises(VaultError, match="wrong master"):
        disable_protection("incorrect-pw")
    assert is_protection_enabled()


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_wrap_json_valid(vault_tmpdir: Path) -> None:
    enable_protection("wrap-check-pw")
    w = load_wrapped_dek()
    assert w is not None
    data = json.loads(
        (vault_tmpdir / "CloneUp" / "secret" / "wrap.json").read_text(encoding="utf-8")
    )
    assert data["v"] == 1
    assert "salt" in data and "wrapped" in data and "verifier" in data


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_corrupted_dpapi_blob_locks(vault_tmpdir: Path) -> None:
    enable_protection("lock-test-pw")
    path = vault_tmpdir / "CloneUp" / "secret" / "dek.dpapi"
    path.write_bytes(b"not-a-valid-dpapi-blob")
    with pytest.raises(VaultLockedError):
        load_dek()


# --- token_store integration -------------------------------------------------


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_token_store_encrypts_when_protection_on(vault_tmpdir: Path) -> None:
    store, _set, _get, _delete = _fake_keyring()
    with (
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch("app.auth.token_store.keyring.delete_password", side_effect=_delete),
        patch("app.auth.token_store.keyring.errors.PasswordDeleteError", Exception),
    ):
        token = "ghp_" + ("e" * 36)
        save_token(token, "repo", auth_kind="pat")
        assert load_token_raw() == token  # plaintext while unprotected

        enable_master_protection("store-master-pw")
        assert master_protection_enabled()
        assert is_token_encrypted()
        raw = load_token_raw()
        assert raw is not None and raw.startswith(TOKEN_ENC_PREFIX)
        assert load_token() == token  # seamless decrypt via DPAPI

        # Re-save while protected → still encrypted
        save_token(token, "repo, workflow", auth_kind="pat")
        assert is_token_encrypted()
        assert load_token() == token

        change_master_password("store-master-pw", "store-master-pw-2")
        assert load_token() == token

        disable_master_protection("store-master-pw-2")
        assert not master_protection_enabled()
        assert load_token_raw() == token
        assert load_token() == token

        delete_token()
        assert load_token() is None


@pytest.mark.skipif(not _WIN, reason="DPAPI only on Windows")
def test_enable_without_existing_token(vault_tmpdir: Path) -> None:
    store, _set, _get, _delete = _fake_keyring()
    with (
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch("app.auth.token_store.keyring.delete_password", side_effect=_delete),
        patch("app.auth.token_store.keyring.errors.PasswordDeleteError", Exception),
    ):
        enable_master_protection("no-token-yet-pw")
        assert master_protection_enabled()
        assert load_token() is None

        token = "github_pat_" + ("z" * 40)
        save_token(token, "repo", auth_kind="pat")
        assert is_token_encrypted()
        assert load_token() == token


def test_plaintext_path_when_protection_off(vault_tmpdir: Path) -> None:
    """Without vault files, save/load stay plaintext (legacy behavior)."""
    store, _set, _get, _delete = _fake_keyring()
    with (
        patch("app.auth.token_store.keyring.set_password", side_effect=_set),
        patch("app.auth.token_store.keyring.get_password", side_effect=_get),
        patch("app.auth.token_store.keyring.delete_password", side_effect=_delete),
        patch("app.auth.token_store.keyring.errors.PasswordDeleteError", Exception),
    ):
        assert not master_protection_enabled()
        token = "ghp_" + ("p" * 36)
        save_token(token, "repo")
        assert load_token_raw() == token
        assert load_token() == token
        assert not is_token_encrypted()


def test_encrypt_for_store_with_injected_dek() -> None:
    dek = generate_dek()
    token = "ghp_" + ("d" * 36)
    enc = encrypt_token_for_store(token, dek=dek)
    assert is_encrypted_blob(enc)
    assert decrypt_token_from_store(enc, dek=dek) == token
