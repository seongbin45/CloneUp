"""Unit tests for independent update_manager (no live GitHub / no kill)."""

from __future__ import annotations

from pathlib import Path

import pytest

from update_manager.apply import _find_onedir_root, copy_onedir_into
from update_manager.github_release import host_allowed
from update_manager.paths import find_cloneup_install_dir
from update_manager.versioning import is_newer, normalize_version


def test_normalize_version_tags() -> None:
    assert normalize_version("v0.1.8") == (0, 1, 8)
    assert normalize_version("0.1.9") == (0, 1, 9)
    assert normalize_version("CloneUp 0.1.8") == (0, 1, 8)
    assert normalize_version("nope") is None


def test_is_newer() -> None:
    assert is_newer((0, 1, 9), (0, 1, 8)) is True
    assert is_newer((0, 1, 8), (0, 1, 8)) is False
    assert is_newer((0, 1, 7), (0, 1, 8)) is False


def test_host_allowed() -> None:
    assert host_allowed("https://github.com/seongbin45/CloneUp/releases/download/x/y.zip")
    assert host_allowed(
        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/x"
    )
    assert not host_allowed("https://evil.example/x.zip")


def _ok_url() -> str:
    return "https://objects.githubusercontent.com/github-production-release-asset-2e65be/x"


class _FakeHeaders(dict):
    def get(self, key, default=None):  # noqa: ANN001
        for k, v in self.items():
            if k.lower() == str(key).lower():
                return v
        return default


class _FakeResp:
    def __init__(self, *, status: int, body: bytes, headers: dict | None = None):
        self.status = status
        self._body = body
        self._pos = 0
        self.headers = _FakeHeaders(headers or {})
        self._fail_after: int | None = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return _ok_url()

    def getcode(self):
        return self.status

    def read(self, n: int = -1):
        if self._pos >= len(self._body):
            if self._fail_after is not None and self._pos >= self._fail_after:
                # Already emitted all allowed bytes; next read stalls.
                raise TimeoutError("The read operation timed out")
            return b""
        if self._fail_after is not None and self._pos >= self._fail_after:
            raise TimeoutError("The read operation timed out")
        if n < 0:
            n = len(self._body) - self._pos
        # Cap this read so mid-stream timeout tests can stop early.
        if self._fail_after is not None:
            n = min(n, max(0, self._fail_after - self._pos))
            if n == 0:
                raise TimeoutError("The read operation timed out")
        chunk = self._body[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk


def test_download_asset_retries_then_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single attempt budget: first connect fails, second delivers full body."""
    import hashlib

    from update_manager import apply as apply_mod

    payload = b"MZ" + b"x" * 100
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    calls = {"n": 0}

    def fake_urlopen(req, context=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("The read operation timed out")
        return _FakeResp(
            status=200,
            body=payload,
            headers={
                "Content-Length": str(len(payload)),
                "ETag": '"abc"',
            },
        )

    monkeypatch.setattr(apply_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(apply_mod.time, "sleep", lambda _s: None)

    dest = tmp_path / "a.zip"
    apply_mod.download_asset(_ok_url(), dest, digest=digest)
    assert calls["n"] == 2
    assert dest.read_bytes() == payload
    assert not Path(str(dest) + ".part").exists()


def test_download_asset_resumes_with_206(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Intra-call Range resume after mid-stream timeout."""
    import hashlib

    from update_manager import apply as apply_mod

    payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    mid = 10
    calls = {"n": 0}
    seen_range: list[str | None] = []

    def _req_hdr(req, name: str) -> str | None:
        # urllib title-cases header keys (e.g. If-range).
        for k, v in req.headers.items():
            if k.lower() == name.lower():
                return v
        return None

    def fake_urlopen(req, context=None, timeout=None):
        calls["n"] += 1
        rng = _req_hdr(req, "Range")
        seen_range.append(rng)
        if calls["n"] == 1:
            resp = _FakeResp(
                status=200,
                body=payload,
                headers={
                    "Content-Length": str(len(payload)),
                    "ETag": '"v1"',
                },
            )
            resp._fail_after = mid
            return resp
        # Resume
        assert rng == f"bytes={mid}-"
        assert _req_hdr(req, "If-Range") == '"v1"'
        return _FakeResp(
            status=206,
            body=payload[mid:],
            headers={
                "Content-Range": f"bytes {mid}-{len(payload)-1}/{len(payload)}",
                "Content-Length": str(len(payload) - mid),
            },
        )

    monkeypatch.setattr(apply_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(apply_mod.time, "sleep", lambda _s: None)

    dest = tmp_path / "a.zip"
    apply_mod.download_asset(_ok_url(), dest, digest=digest)
    assert calls["n"] == 2
    assert seen_range[1] == f"bytes={mid}-"
    assert dest.read_bytes() == payload


def test_download_asset_200_on_resume_truncates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CDN ignores Range / If-Range → truncate, never append (HF corruption case)."""
    import hashlib

    from update_manager import apply as apply_mod

    payload = b"FULLFILECONTENT_OK_123456"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    calls = {"n": 0}

    def fake_urlopen(req, context=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            resp = _FakeResp(
                status=200,
                body=payload,
                headers={"Content-Length": str(len(payload)), "ETag": '"e"'},
            )
            resp._fail_after = 5
            return resp
        # Server returns full body again (200) despite Range
        return _FakeResp(
            status=200,
            body=payload,
            headers={"Content-Length": str(len(payload)), "ETag": '"e"'},
        )

    monkeypatch.setattr(apply_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(apply_mod.time, "sleep", lambda _s: None)

    dest = tmp_path / "a.zip"
    apply_mod.download_asset(_ok_url(), dest, digest=digest)
    assert dest.read_bytes() == payload  # not doubled


def test_download_asset_digest_mismatch_clears_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from update_manager import apply as apply_mod

    payload = b"MZ" + b"y" * 20

    def fake_urlopen(req, context=None, timeout=None):
        return _FakeResp(
            status=200,
            body=payload,
            headers={"Content-Length": str(len(payload)), "ETag": '"z"'},
        )

    monkeypatch.setattr(apply_mod.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "a.zip"
    with pytest.raises(RuntimeError, match="digest mismatch"):
        apply_mod.download_asset(_ok_url(), dest, digest="sha256:" + ("0" * 64))
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_download_asset_requires_digest(tmp_path: Path) -> None:
    from update_manager import apply as apply_mod

    with pytest.raises(RuntimeError, match="digest missing"):
        apply_mod.download_asset(_ok_url(), tmp_path / "a.zip", digest=None)


def test_download_asset_206_without_content_range_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from update_manager import apply as apply_mod

    payload = b"0123456789ABCDEF"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    calls = {"n": 0}

    def fake_urlopen(req, context=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            resp = _FakeResp(
                status=200,
                body=payload,
                headers={"Content-Length": str(len(payload)), "ETag": '"t"'},
            )
            resp._fail_after = 4
            return resp
        # Bad 206 (no Content-Range) → code must restart; next attempt full 200
        if calls["n"] == 2:
            return _FakeResp(status=206, body=payload[4:], headers={})
        return _FakeResp(
            status=200,
            body=payload,
            headers={"Content-Length": str(len(payload)), "ETag": '"t"'},
        )

    monkeypatch.setattr(apply_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(apply_mod.time, "sleep", lambda _s: None)
    dest = tmp_path / "a.zip"
    apply_mod.download_asset(_ok_url(), dest, digest=digest)
    assert dest.read_bytes() == payload
    assert calls["n"] == 3


def test_find_install_dir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "CloneUp"
    app.mkdir()
    (app / "CloneUp.exe").write_bytes(b"MZ")
    monkeypatch.setenv("CLONEUP_INSTALL_DIR", str(app))
    got = find_cloneup_install_dir()
    assert got is not None
    assert got == app.resolve()


def test_find_install_dir_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CLONEUP_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    # Empty registry scan may still find a real install on this machine —
    # only assert env override path works when set; for missing, call is allowed.
    # Force env empty dir that does not look like install:
    bad = tmp_path / "empty"
    bad.mkdir()
    monkeypatch.setenv("CLONEUP_INSTALL_DIR", str(bad))
    assert find_cloneup_install_dir() is None


def test_copy_onedir_flat(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "CloneUp.exe").write_text("exe", encoding="utf-8")
    (src / "VERSION").write_text("0.1.9\n", encoding="utf-8")
    sub = src / "_internal"
    sub.mkdir()
    (sub / "x.txt").write_text("1", encoding="utf-8")

    dest = tmp_path / "install"
    dest.mkdir()
    (dest / "old.txt").write_text("old", encoding="utf-8")

    copy_onedir_into(src, dest)
    assert (dest / "CloneUp.exe").read_text(encoding="utf-8") == "exe"
    assert (dest / "VERSION").read_text(encoding="utf-8").startswith("0.1.9")
    assert (dest / "_internal" / "x.txt").is_file()
    assert not (dest / "old.txt").exists()


def test_copy_preserves_unins(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "CloneUp.exe").write_text("new", encoding="utf-8")
    dest = tmp_path / "install"
    dest.mkdir()
    (dest / "unins000.exe").write_bytes(b"UNINS")
    (dest / "unins000.dat").write_bytes(b"DAT")
    (dest / "CloneUp.exe").write_text("old", encoding="utf-8")

    copy_onedir_into(src, dest)
    assert (dest / "CloneUp.exe").read_text(encoding="utf-8") == "new"
    assert (dest / "unins000.exe").read_bytes() == b"UNINS"
    assert (dest / "unins000.dat").read_bytes() == b"DAT"


def test_cloneup_exe_running_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    from update_manager import process_win as pw

    class R:
        def __init__(self, stdout: bytes):
            self.stdout = stdout

    def fake_run(*_a, **_k):
        # Korean "no matching tasks" message (cp949), no CloneUp.exe
        return R(
            b"\xc1\xa4\xba\xb8: \xbd\xc7\xc7\xe0 \xc1\xdf\xc0\xce "
            b"\xc0\xdb\xbe\xf7 \xc1\xdf \xc1\xf6\xc1\xa4\xb5\xc8 "
            b"\xc1\xb6\xb0\xc7\xbf\xa1 \xc0\xcf\xc4\xa1\xc7\xcf\xb4\xc2 "
            b"\xc0\xdb\xbe\xf7\xc0\xcc \xbe\xf8\xbd\xc0\xb4\xcf\xb4\xd9.\r\n"
        )

    monkeypatch.setattr(pw.subprocess, "run", fake_run)
    assert pw._cloneup_exe_running() is False

    def fake_run_hit(*_a, **_k):
        return R(b"CloneUp.exe                  1234 Console    1    50,000 K\r\n")

    monkeypatch.setattr(pw.subprocess, "run", fake_run_hit)
    assert pw._cloneup_exe_running() is True


def test_find_onedir_root_nested(tmp_path: Path) -> None:
    root = tmp_path / "extract"
    nested = root / "CloneUp"
    nested.mkdir(parents=True)
    (nested / "CloneUp.exe").write_bytes(b"MZ")
    assert _find_onedir_root(root) == nested
