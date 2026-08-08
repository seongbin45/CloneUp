# 로그 우선 원칙 (Logging-First) — 개발자 안내

작성 계기: `app/github/api_client.compare_remote_commits`의 방향 버그(되돌리기 미리보기가
"바뀌는 파일이 없습니다"를 잘못 보고)를 진단할 때, 터미널에도 앱 로그창에도 아무 단서가
없어서 실행 중인 앱을 화면 접근성 트리로 직접 찔러보며 원인을 찾아야 했다. 코드를 훑어보니
이건 우연이 아니라 구조적인 공백이었다 — 이 문서는 그 공백을 코드 수준에서 교차검증한
결과와, 앞으로 지킬 규칙을 정리한다.

## 1. 지금 상태 (교차검증 결과, 파일:줄 근거)

| 동작 | 터미널에 나오는가 | 앱 로그창(`textLog`)에 나오는가 | 근거 |
|---|---|---|---|
| 만들고 올리기 (Publish) | **아니오** | 예 | `app/ui/publish_worker.py:64-66` — `redirect_stdout`/`redirect_stderr`가 워커 실행 동안 `sys.stdout`을 **교체**함 |
| GitHub 로그인 (Device Flow / PAT) | **아니오** | 예 | `app/ui/publish_worker.py:125-127`, `:193-195` (동일 패턴) |
| 받기 (Clone) | **아니오** | 예 | `app/ui/tab_workers.py:73-75` |
| 동기화 — 올리고 보내기 / 받아오기 / 충돌 취소 | **아니오** | 예 | `app/ui/tab_workers.py:181-183` |
| 동기화 — 상태 새로고침 | **아니오** | **아니오** | `app/ui/tab_workers.py:121-149` `SyncStatusWorker` — `redirect_stdout` 자체가 없고, `log_line` 시그널을 선언만 하고 한 번도 `emit`하지 않음. `app/git/sync_ops.get_repo_status()`에는 애초에 `print()`가 없어 지금은 우연히 무해함 |
| Git 미설치 시 자동 설치 | **아니오** | **아니오** | `app/ui/git_setup.py`의 `_DownloadWorker` — redirect 없음, `download_and_run_git_installer`도 로그 시그널 없이 진행률만 전달 |
| **커밋 내역 조회 (로컬/원격 목록·상세)** | **아니오** | **아니오** | `app/ui/commit_history_dialog.py`의 `_LoadWorker`/`_DetailWorker`/`_ExportWorker` — `_SignalStdout` 자체를 쓰지 않음. 애초에 `app/git/history.py`, `app/github/api_client.py`에 `print()`가 **하나도 없음** |
| **되돌리기 미리보기 / 실행 (로컬·원격 모두)** | **아니오** | **아니오** | `_RevertPreviewWorker`/`_RevertWorker` — 위와 동일. `app/git/revert.py`에도 `print()`가 **하나도 없음** |

요약: "로그창에는 나온다"고 해도 그건 **터미널에는 나오지 않는다는 뜻**이다. 그리고 커밋
내역·되돌리기 전체 기능은 로그창에도 안 나온다 — 완전히 조용하다. `CommitHistoryDialog`는
메인 창의 `textLog`와 아예 연결되어 있지 않다 (별도 `QDialog`이고, `_log()` 호출부는
`app/ui/main_window.py`에만 있음).

## 2. 왜 이렇게 됐는가 (근본 원인)

### 2.1 `redirect_stdout`은 "복제(tee)"가 아니라 "교체(swap)"다

```python
# app/ui/tab_workers.py:73-75 (publish_worker.py도 동일 패턴)
sink = _SignalStdout(self._log)
with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
    ...  # 이 블록 안의 print()는 전부 sink로만 감. 진짜 터미널엔 안 감.
```

`contextlib.redirect_stdout`은 `sys.stdout`을 블록이 끝날 때까지 **다른 객체로 바꿔치기**
한다. 원래 스트림에도 동시에 쓰는 기능이 없다. 그래서 이 블록 안에서 실행되는 모든 `print()`는
앱 로그창에만 가고, 콘솔에서 `python main.py`로 띄워도 콘솔에는 절대 안 보인다.

**추가 위험**: `sys.stdout`은 프로세스 전역(하나) 변수이지, 스레드별 변수가 아니다. 워커 A가
`redirect_stdout` 블록 안에 있는 동안 워커 B(또는 메인 스레드)가 `print()`를 호출하면, 그
줄도 A의 `sink`로 흘러 들어간다 — 즉 서로 다른 작업의 로그가 섞일 수 있는 구조다. 지금은
`_busy()` 가드로 동시 실행을 막아 우연히 드러나지 않을 뿐, 구조 자체는 스레드 안전하지 않다.

### 2.2 `_SignalStdout`이 두 곳에 복사돼 있다

`app/ui/tab_workers.py:23-43`와 `app/ui/publish_worker.py:22-42`에 **거의 동일한 클래스가
두 벌** 있다. 한쪽만 고치면 다른 쪽은 그대로 남는다 — 이번 감사에서 실제로 그런 드리프트
위험을 확인했다 (다행히 지금은 둘 다 `mask_secrets_in_text`를 쓰고 있어 동작은 같다).

### 2.3 조용한 모듈들

`app/git/revert.py`, `app/git/history.py`, `app/github/api_client.py`는 `print()`를 한 번도
쓰지 않는다. `app/git/publish.py`, `app/git/sync_ops.py`, `app/auth/session.py`,
`app/git/clone_ops.py`는 주요 단계마다 `print()`를 남긴다 (예:
`app/git/publish.py:339` `"GitHub로 보내는 중…"`). 이 비대칭이 곧 "커밋 내역·되돌리기만
디버그 흔적이 없다"는 증상으로 나타났다.

### 2.4 새 팝업(`QDialog`)은 로그 배선이 기본값이 아니다

`CommitHistoryDialog`를 만들 때 `main_window.py`의 로그 배선(`_SignalStdout` → `log_line`
시그널 → `self._log()`)을 그대로 가져오지 않았다. `QMessageBox`로 성공/실패는 사용자에게
보여주지만, **그 사이에 무슨 일이 있었는지에 대한 지나간 기록이 전혀 남지 않는다** — 실패
원인을 재현 없이 사후에 알아낼 방법이 없다는 뜻.

## 3. 원칙 (앞으로 지킬 것)

1. **모든 실행 가능한 동작은 시작·성공·실패 세 시점에 최소 한 줄씩 로그를 남긴다.**
   버튼 클릭이든 백그라운드 워커든 예외 없음. "조용히 성공/실패"는 없다.
2. **로그는 터미널과 앱 로그창 양쪽에 항상 동시에 나가야 한다.** 교체(swap)가 아니라
   복제(tee) — 아래 3.1 참고.
3. **비밀·토큰은 항상 `app.util.log_mask.mask_secrets_in_text`(또는 `mask_token`)를 거친
   뒤에만 로그로 내보낸다.** 지금 코드가 이미 이 규칙은 잘 지키고 있다 — 새 로그를 추가할 때도
   똑같이.
4. **새 `QThread` 워커/새 `QDialog`를 만들 때, "이 작업이 실패하면 사용자가 왜 실패했는지
   로그만 보고 알 수 있는가?"를 설계 단계에서 먼저 답한다.** 나중에 로그를 붙이지 않는다 —
   `CommitHistoryDialog`가 정확히 그 반례다.
5. **순수 로직 모듈(`app/git/*.py`, `app/github/*.py`)에 상태 전환마다 `print()`를 남긴다.**
   이 모듈들은 UI와 무관하게 CLI 스파이크(`spike_*.py`)에서도 그대로 재사용되므로, 여기 있는
   로그가 곧 "무엇을 했는지"의 1차 기록이 된다.

## 4. 구현 패턴

### 4.1 `_SignalStdout`을 진짜 tee로 바꾸기 (swap → tee)

지금:

```python
def write(self, s: str) -> int:
    ...
    self._emit(mask_secrets_in_text(line))
    return len(s)
```

바꿀 방향 — 원래 스트림에도 쓰고, 시그널도 보낸다:

```python
class _SignalStdout(io.TextIOBase):
    def __init__(self, emit_line, *, mirror=None) -> None:
        super().__init__()
        self._emit = emit_line
        self._mirror = mirror  # 원래 sys.__stdout__ / sys.__stderr__
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._mirror is not None:
            self._mirror.write(s)  # 콘솔에도 그대로
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self._emit(mask_secrets_in_text(line))
        return len(s)
```

호출부에서 `sys.__stdout__`/`sys.__stderr__`(리다이렉트 전 원본)를 넘긴다. 마스킹은 로그창
쪽(`_emit`)에만 적용되므로, 콘솔 쪽 마스킹이 필요하면 `mirror.write`에도 같은 처리를 씌운다 —
콘솔 로그도 결국 화면 공유·캡처될 수 있으므로 토큰은 콘솔에도 마스킹해서 내보내는 쪽을
권장한다.

두 사본(`tab_workers.py`, `publish_worker.py`) 중 하나를 공용 모듈(예: `app/ui/log_sink.py`)로
옮기고 둘 다 그걸 import하도록 정리하면 드리프트 위험도 같이 없앨 수 있다.

### 4.2 조용한 모듈에 로그 추가하기

`app/git/revert.py` 예시 — 단계 경계마다 한 줄:

```python
def revert_local_commit(folder, target_rev, *, user, hide_real_email=False):
    ...
    print(f"되돌리기 시작: {target_rev} → {root}")
    ...
    print(f"백업 브랜치 생성: {backup_branch}")
    ...
    print(f"되돌리기 커밋 완료: {new_commit[:7]}")
    return RevertResult(...)
```

`revert_to_commit`/`revert_remote_commit`의 push 단계, `app/git/history.py`의
`list_commits`/`export_commit_snapshot`, `app/github/api_client.py`의 각 API 호출부에도
동일하게 시작/결과 한 줄씩.

### 4.3 `CommitHistoryDialog`를 로그창에 연결하기

가장 간단한 방법 — 다이얼로그 생성 시 로그 콜백을 주입받는다:

```python
class CommitHistoryDialog(QDialog):
    def __init__(self, parent, *, folder=None, ..., log: Callable[[str], None] | None = None):
        ...
        self._log = log or (lambda _msg: None)
```

그리고 각 워커의 `run()`에도 `_SignalStdout` + `redirect_stdout`(tee 버전)을 씌우고,
`log_line` 시그널을 `self._log`로 연결한다 — `tab_workers.py`의 기존 워커들과 동일한 패턴.
`show_commit_history`/`show_remote_commit_history` 호출부(`main_window.py`)에서
`log=self._log`를 넘기면, 다이얼로그 안에서 벌어지는 일도 메인 창 로그창에 이어서 쌓인다.

### 4.4 `SyncStatusWorker`

`log_line` 시그널이 선언만 되고 미사용 상태다. `get_repo_status()` 호출 전후로 한 줄씩
`self.log_line.emit(...)`을 추가하고, 호출부(`main_window.py`)에서 다른 워커들처럼
`worker.log_line.connect(self._log)`를 연결한다.

## 5. 새 기능 추가 시 체크리스트

- [ ] 이 작업을 실행하는 `QThread`가 있다면, 시작할 때 최소 한 줄 로그를 남기는가?
- [ ] 성공 시 결과(무엇을 했는지, 어떤 값이 나왔는지)를 한 줄로 남기는가?
- [ ] 실패 시 원인을 한 줄로 남기는가 (예외 메시지 그대로 노출 전 `mask_secrets_in_text` 통과)?
- [ ] 이 로그가 **터미널**과 **앱 로그창** 양쪽에 실제로 도달하는가 (교체가 아니라 복제인가)?
- [ ] 토큰·비밀번호·PAT가 로그 문자열에 그대로 섞여 나가지 않는가?
- [ ] 새 팝업(`QDialog`)이라면 메인 창 로그창과 연결했는가, 아니면 최소한 자체 로그 영역이
      있는가?

## 6. 참고

- 마스킹 유틸: `app/util/log_mask.py` (`mask_token`, `mask_secrets_in_text`)
- 기존에 잘 되어 있는 예시: `app/git/publish.py`, `app/git/sync_ops.py`,
  `app/auth/session.py` — 단계 경계마다 `print()` 한 줄씩 남기는 패턴을 그대로 따라가면 된다.
- 이 문서가 다루는 범위는 "로그가 도달하는가"이다. 로그 문구의 톤·용어(초심자 친화적 한국어)는
  `docs/UX_GUIDANCE.md`를 따른다.
