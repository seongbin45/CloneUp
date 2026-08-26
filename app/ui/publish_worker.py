"""Background publish / login jobs — never run git/network on the UI thread."""

from __future__ import annotations

import contextlib
import io
import re
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


class LoginWorker(QThread):
    """Force Device Flow login (browser)."""

    log_line = Signal(str)
    # UI thread should show DeviceCodeOverlay (main-thread clipboard/browser).
    user_code_ready = Signal(str, str, int)  # user_code, verification_uri, expires_in
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, force: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.force = force

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def run(self) -> None:
        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                if self.isInterruptionRequested():
                    self.failed.emit("취소됨")
                    return
                self._log("GitHub 로그인 (개발용 Device Flow)…")

                def on_user_code(code: str, uri: str, expires_in: int) -> None:
                    self.user_code_ready.emit(code, uri, int(expires_in))

                token, user = ensure_valid_token(
                    force_login=self.force,
                    open_browser=False,
                    copy_code=False,
                    on_user_code=on_user_code,
                    should_cancel=self.isInterruptionRequested,
                )
                if self.isInterruptionRequested():
                    self.failed.emit("로그인이 취소되었습니다.")
                    return
                self.succeeded.emit(
                    {
                        "login": user.get("login"),
                        "scope": load_scope(),
                        "token_masked": mask_token(token),
                        "auth_kind": "device",
                    }
                )
        except AuthError as e:
            msg = str(e)
            if "취소" in msg:
                self.failed.emit(msg)
            else:
                # Keep Device Flow detail (avoid opaque "인증 실패" only)
                self.failed.emit(f"Device 인증 실패: {e}")
        except OSError as e:
            self.failed.emit(f"네트워크: {e}")
        except Exception as e:
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))
        finally:
            sink.flush()


class PatLoginWorker(QThread):
    """Validate and store a user-supplied Personal Access Token (no OAuth App)."""

    log_line = Signal(str)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(
        self, token: str, parent=None, *, expires_at: str | None = None
    ) -> None:
        super().__init__(parent)
        self._token = token
        self._expires_at = expires_at

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def run(self) -> None:
        from app.auth.session import login_with_pat
        from app.auth.token_expiry import format_expires_display
        from app.auth.token_store import load_expires_at_raw

        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                if self.isInterruptionRequested():
                    self.failed.emit("취소됨")
                    return
                self._log("GitHub 키로 연결 중…")
                token, user = login_with_pat(
                    self._token, expires_at=self._expires_at
                )
                if self.isInterruptionRequested():
                    self.failed.emit("연결이 취소되었습니다.")
                    return
                exp = user.get("_expires_at") or load_expires_at_raw()
                self.succeeded.emit(
                    {
                        "login": user.get("login"),
                        "scope": load_scope(),
                        "token_masked": mask_token(token),
                        "auth_kind": "pat",
                        "expires_at": exp,
                        "expires_display": format_expires_display(
                            str(exp) if exp else None
                        ),
                    }
                )
        except AuthError as e:
            self.failed.emit(str(e))
        except OSError as e:
            self.failed.emit(f"네트워크 오류: {e}")
        except Exception as e:
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))
        finally:
            sink.flush()


class PublishWorker(QThread):
    log_line = Signal(str)
    user_code_ready = Signal(str, str, int)
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
        hide_real_email: bool = True,
        default_branch: str = "main",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.folder = folder
        self.repo_name = repo_name
        self.commit_message = commit_message
        self.private = private
        self.allow_secrets = allow_secrets
        self.hide_real_email = hide_real_email
        self.default_branch = default_branch or "main"

    def _log(self, msg: str) -> None:
        self.log_line.emit(mask_secrets_in_text(msg))

    def _cancelled(self) -> bool:
        if self.isInterruptionRequested():
            self.failed.emit(
                "취소됨. (이미 push가 시작된 경우 원격에 일부 반영됐을 수 있습니다)"
            )
            return True
        return False

    def run(self) -> None:
        sink = _SignalStdout(self._log)
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                self._run_body()
        except Exception as e:
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
        self._log(
            f"시작: {folder} → GitHub/{name} "
            f"({'비공개' if self.private else '공개'})"
        )
        if self._cancelled():
            return

        try:
            self._log("연결 확인 중…")

            # Never auto-start Device Flow — PAT must already be in keyring.
            token, user = ensure_valid_token(
                open_browser=False,
                copy_code=False,
                should_cancel=self.isInterruptionRequested,
            )
            self._log(f"연결됨: {user.get('login')}")
        except AuthError as e:
            self.failed.emit(f"연결 실패: {e}")
            return
        except OSError as e:
            self.failed.emit(f"네트워크 오류: {e}")
            return

        if self._cancelled():
            return

        try:
            result: PublishResult = publish_folder_to_new_repo(
                folder,
                token=token,
                user=user,
                create_repo_fn=create_repo,
                repo_name=name,
                description="Published with CloneUp",
                commit_message=self.commit_message or "첫 업로드",
                allow_secrets=self.allow_secrets,
                private=self.private,
                hide_real_email=self.hide_real_email,
                default_branch=self.default_branch,
            )
        except PublishError as e:
            if self.isInterruptionRequested():
                self.failed.emit("취소됨")
            else:
                self.failed.emit(str(e))
            return
        except GitError as e:
            self.failed.emit(f"Git 오류: {e}")
            return
        except OSError as e:
            self.failed.emit(f"네트워크 오류: {e}")
            return

        if self._cancelled():
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
        self._log(f"완료: {result.html_url}")
        self.succeeded.emit(payload)
