"""Background publish job — never run git/network on the UI thread."""

from __future__ import annotations

import contextlib
import io
import re
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.auth.session import AuthError, ensure_valid_token
from app.auth.token_store import load_scope
from app.git.publish import PublishError, PublishResult, publish_folder_to_new_repo
from app.git.runner import GitError
from app.github.api_client import create_repo
from app.util.log_mask import mask_secrets_in_text, mask_token

_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class _SignalStdout(io.TextIOBase):
    """Forward print() from worker thread into a Qt signal (token-masked)."""

    def __init__(self, emit_line) -> None:
        super().__init__()
        self._emit = emit_line
        self._buf = ""

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self._emit(mask_secrets_in_text(line))
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._emit(mask_secrets_in_text(self._buf.rstrip()))
        self._buf = ""


class PublishWorker(QThread):
    log_line = Signal(str)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        *,
        folder: str,
        repo_name: str,
        commit_message: str,
        private: bool,
        allow_secrets: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.folder = folder
        self.repo_name = repo_name
        self.commit_message = commit_message
        self.private = private
        self.allow_secrets = allow_secrets

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def run(self) -> None:  # noqa: PLR0911
        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                self._run_body()
        except Exception as e:  # last-resort — keep UI alive
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))
        finally:
            sink.flush()

    def _run_body(self) -> None:
        folder = Path(self.folder).expanduser().resolve()
        name = self.repo_name.strip()
        if not name:
            self.failed.emit("저장소 이름을 입력하세요.")
            return
        if not _REPO_NAME_RE.match(name):
            self.failed.emit("저장소 이름은 영문/숫자/._- 만 사용할 수 있습니다.")
            return
        if not folder.is_dir():
            self.failed.emit(f"폴더가 없습니다: {folder}")
            return

        vis = "private" if self.private else "public"
        self._log(f"시작: {folder} → GitHub/{name} ({vis})")

        try:
            self._log("인증 확인 (필요 시 브라우저 Device Flow)…")
            token, user = ensure_valid_token(open_browser=True)
            self._log(f"로그인: {user.get('login')} · scope={load_scope()!r}")
            self._log(f"토큰: {mask_token(token)}")
        except AuthError as e:
            self.failed.emit(f"인증 실패: {e}")
            return
        except OSError as e:
            self.failed.emit(f"네트워크: {e}")
            return

        try:
            result: PublishResult = publish_folder_to_new_repo(
                folder,
                token=token,
                user=user,
                create_repo_fn=create_repo,
                repo_name=name,
                description="Published with CloneUp",
                commit_message=self.commit_message or "Initial commit",
                allow_secrets=self.allow_secrets,
                private=self.private,
            )
        except PublishError as e:
            self.failed.emit(str(e))
            return
        except GitError as e:
            self.failed.emit(f"git: {e}")
            return
        except OSError as e:
            self.failed.emit(f"네트워크: {e}")
            return

        payload = {
            "folder": str(result.folder),
            "full_name": result.full_name,
            "html_url": result.html_url,
            "clone_url": result.clone_url,
            "commit_message": result.commit_message,
            "config_clean": result.config_clean,
            "private": self.private,
        }
        self._log(f"완료: {result.html_url} (config_clean={result.config_clean})")
        self.succeeded.emit(payload)
