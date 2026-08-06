"""Background workers for Clone / Sync tabs."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.auth.session import AuthError, ensure_valid_token
from app.git.clone_ops import CloneError, clone_repository
from app.git.sync_ops import (
    SyncError,
    abort_merge,
    commit_and_push,
    get_repo_status,
    pull_repo,
)
from app.util.log_mask import mask_secrets_in_text, mask_token


class _SignalStdout(io.TextIOBase):
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


class CloneWorker(QThread):
    log_line = Signal(str)
    user_code_ready = Signal(str, str, int)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        *,
        url: str,
        parent_dir: str,
        dir_name: str,
        use_token: bool,
        branch: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.parent_dir = parent_dir
        self.dir_name = dir_name
        self.use_token = use_token
        self.branch = (branch or "").strip() or None

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def run(self) -> None:
        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                if self.isInterruptionRequested():
                    self.failed.emit("취소됨")
                    return
                token = None
                if self.use_token:
                    self._log("인증 확인 (비공개 저장소 받기)…")
                    token, user = ensure_valid_token(
                        open_browser=False,
                        copy_code=False,
                        should_cancel=self.isInterruptionRequested,
                    )
                    self._log(f"연결됨: {user.get('login')}")
                if self.isInterruptionRequested():
                    self.failed.emit("취소됨")
                    return
                name = self.dir_name.strip() or None
                if self.branch:
                    self._log(f"브랜치: {self.branch}")
                else:
                    self._log("브랜치: 기본 브랜치")
                result = clone_repository(
                    self.url,
                    Path(self.parent_dir),
                    directory_name=name,
                    token=token,
                    branch=self.branch,
                )
                self.succeeded.emit(
                    {
                        "path": str(result.target_dir),
                        "clone_url": result.clone_url,
                        "owner": result.owner,
                        "repo": result.repo,
                        "branch": self.branch or "",
                        "warnings": list(result.warnings),
                    }
                )
        except (CloneError, AuthError, OSError) as e:
            self.failed.emit(mask_secrets_in_text(str(e)))
        except Exception as e:
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))
        finally:
            sink.flush()


class SyncStatusWorker(QThread):
    log_line = Signal(str)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, folder: str, parent=None) -> None:
        super().__init__(parent)
        self.folder = folder

    def run(self) -> None:
        try:
            st = get_repo_status(Path(self.folder))
            self.succeeded.emit(
                {
                    "summary": st.summary,
                    "branch": st.branch,
                    "has_origin": st.has_origin,
                    "origin_url": st.origin_url,
                    "dirty": st.dirty,
                    "conflict": st.conflict,
                    "folder": str(st.folder),
                }
            )
        except SyncError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(mask_secrets_in_text(str(e)))


class SyncActionWorker(QThread):
    """pull | push | abort"""

    log_line = Signal(str)
    user_code_ready = Signal(str, str, int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        action: str,
        folder: str,
        message: str = "",
        allow_secrets: bool = False,
        hide_real_email: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.action = action
        self.folder = folder
        self.message = message
        self.allow_secrets = allow_secrets
        self.hide_real_email = hide_real_email

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def run(self) -> None:
        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                folder = Path(self.folder)

                auth_kw = dict(
                    open_browser=False,
                    copy_code=False,
                    should_cancel=self.isInterruptionRequested,
                )
                if self.action == "pull":
                    self._log("받아오기…")
                    token, _user = ensure_valid_token(**auth_kw)
                    msg = pull_repo(folder, token=token)
                    self.succeeded.emit(msg)
                elif self.action == "push":
                    self._log("올리고 보내기…")
                    token, user = ensure_valid_token(**auth_kw)
                    msg = commit_and_push(
                        folder,
                        message=self.message,
                        token=token,
                        user=user,
                        allow_secrets=self.allow_secrets,
                        hide_real_email=self.hide_real_email,
                    )
                    self.succeeded.emit(msg)
                elif self.action == "abort":
                    self._log("겹친 상태 되돌리는 중…")
                    msg = abort_merge(folder)
                    self.succeeded.emit(msg)
                else:
                    self.failed.emit(f"알 수 없는 동작: {self.action}")
        except (SyncError, AuthError, OSError) as e:
            self.failed.emit(mask_secrets_in_text(str(e)))
        except Exception as e:
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))
        finally:
            sink.flush()
