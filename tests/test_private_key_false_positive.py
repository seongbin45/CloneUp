"""
Regression: a README merely mentioning the PEM header line (e.g. explaining
key format, or showing it as a docs example) must not hard-block publish
forever — private_key has no allow_secrets bypass, so a false positive here
is unrecoverable without editing the file. Only a real BEGIN...END block
(what an actually-leaked key file always has) should count.
"""

from __future__ import annotations

from pathlib import Path

from app.git.safety import run_safety_checks, scan_secret_in_contents


def test_readme_mentioning_pem_header_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "SSH 개인 키는 -----BEGIN RSA PRIVATE KEY----- 로 시작합니다.\n",
        encoding="utf-8",
    )
    hits = scan_secret_in_contents(tmp_path)
    assert not any(h.kind == "private_key" for h in hits), hits

    report = run_safety_checks(tmp_path, allow_secrets=False, write_gitignore=False)
    assert report.ok, report.errors


def test_real_pem_block_is_still_hard_blocked(tmp_path: Path) -> None:
    (tmp_path / "id_rsa").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAtest\n"
        "-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    hits = scan_secret_in_contents(tmp_path)
    assert any(h.kind == "private_key" for h in hits), hits

    report = run_safety_checks(tmp_path, allow_secrets=False, write_gitignore=False)
    assert not report.ok

    # H1: hard content secrets cannot be bypassed via allow_secrets
    allowed = run_safety_checks(tmp_path, allow_secrets=True, write_gitignore=False)
    assert not allowed.ok
