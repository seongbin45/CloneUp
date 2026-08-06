# CloneUp 보안 리뷰 (외부 검토)

대상: `seongbin45/CloneUp` @ main (72 commits, v0.1.2)
방법: 전체 소스 정독 + 실제 실행 재현(git 2.43, 스캐너 직접 호출)
검토 관점: 이 앱은 **사용자 GitHub 토큰을 들고, 사용자가 지정한 임의 폴더에서 git을 실행하고, 인터넷에서 .exe를 받아 실행**한다. 이 세 축을 기준으로 봤다.

> **조치 상태 (2026-08-07, 로컬 재현 후 패치)**  
> - **H1** 수정: 스캔 대상 = `git ls-files -co --exclude-standard` (gitignore 존중), `.github` 스캔, hard content 키는 `allow_secrets`로 우회 불가  
> - **H2** 수정: `store --file='…'` 인용 + 위험 문자 거부 + `%LOCALAPPDATA%\CloneUp\tmp`  
> - **H3** 수정: 서명 검사 fail-open 제거, 빈 subject 거부, PowerShell/clip 절대경로  
> - **M1** stdout 마스킹 적용 · **M2** `_TOKEN_LEAK_RE`에 `ghp_` 포함  
> - **M4** `run_git` 안전 `-c` (hooksPath 빈 디렉터리, pager=cat, fsmonitor off) + `commit --no-verify`  
> - **M5** 기본 비공개 (`last_private` / UI radio / API default)  
> - **P2 origin** sync pull/push 전 `assert_github_https_remote`  
> - 회귀: `tests/` + `verify_*` + GitHub Actions CI  
> - 잔여: 코드 서명(P2/M6), requirements hash pin, Device Flow 릴리스 빌드 제외

---

## 총평

가장 큰 문제는 인증이나 토큰 저장이 아니다. 그쪽은 꽤 방어적으로 짜여 있다
(토큰 argv 미노출, `.git/config` 잔류 검사, 임시 credential 파일 wipe+삭제, Device Flow 기본 비활성).

문제는 **제품의 핵심 차별점이라고 내세운 「초보 실수 방지 안전검사」가 실제로는 잘못된 대상을 검사한다**는 것이다.
진짜 유출은 통과시키고, 유출이 아닌 것은 차단한다. 그리고 그 오탐을 해소하는 UI 버튼이 진짜 방어까지 같이 끈다.
보안 기능이 없는 것보다 나쁘다 — 사용자에게 "검사 통과 = 안전"이라는 잘못된 확신을 준다.

| 등급 | 건수 | 항목 |
|---|---|---|
| P0 (릴리스 차단) | 3 | H1 안전검사 대상 불일치, H2 credential 경로 셸 주입, H3 서명검증 fail-open |
| P1 | 5 | M1 stdout 미마스킹, M2 토큰 정규식 불일치, M4 타 저장소 설정 신뢰, M5 과잉 권한·public 기본, M6 미서명 설치파일 |
| P2 | 6 | M3 origin 호스트 미검증, L1~L5 |

---

# P0 — 릴리스 전 반드시

## H1. 안전검사가 "커밋될 파일"이 아니라 "파일시스템"을 검사한다

**위치:** `app/git/safety.py` (`run_safety_checks`, `scan_secret_in_contents`, `find_secret_candidates`), `app/git/sync_ops.py:commit_and_push`

**교차검증 — 실제로 돌려본 결과 (양방향 모두 틀림):**

```
# 1) 진짜 유출이 통과한다
/tmp/t/.github/workflows/deploy.yml  →  AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'
content hits : []
name hits    : []
safety ok?   : True []          ← 통과. 그리고 git add -A 는 .github/ 를 커밋한다.

# 2) 유출이 아닌 것이 차단된다
/tmp/t2/node_modules/foo/credentials.js  (.gitignore 에 node_modules/ 있음)
ok? False
errors: ['비밀 파일로 보이는 항목이 있습니다 … node_modules/foo/credentials.js']
```

**원인 세 가지**

1. `_should_skip_dir()` (safety.py:218) 가 `name.startswith(".")` 로 **모든 점 디렉터리를 내용 스캔에서 제외**한다.
   `.github/`, `.config/`, `.aws/`, `.circleci/`, `.vscode/` — 전부 커밋되는데 전부 스캔 제외다.
2. 스캔 기준이 `os.walk` 파일시스템이라 **.gitignore 를 전혀 모른다.** `node_modules`, `dist`, `.venv` 안의 파일까지 차단 사유로 센다.
3. 그래서 사용자는 정상 프로젝트에서 계속 막힌다 → UI의 「비밀 파일도 커밋 (고급)」/`allow_secrets` 를 켠다 →
   이 스위치 하나가 **이름 검사와 내용 검사를 동시에** 끈다 (`run_safety_checks` 의 두 블록, `sync_ops.py` 의 단일 `if`).
   즉 오탐이 사용자를 훈련시켜 진짜 방어를 끄게 만든다.

**추가:** `_MAX_FILES_SCANNED = 2000` 에 걸리면 조용히 중단하고 "이상 없음"으로 보고한다. 대형 폴더는 사실상 미검사인데 UI는 통과라고 말한다.

**수정 (순서대로)**

1. 스캔 대상을 git 에게 물어본다. `git add -A` 를 먼저 하고:
   ```python
   r = run_git(["diff", "--cached", "--name-only", "-z"], cwd=str(folder))
   staged = [p for p in r.stdout.split("\0") if p]
   ```
   이 목록만 스캔한다. (clone 후 sync 경로도 동일)
2. `_should_skip_dir` 에서 `name.startswith(".")` 제거. `.git` 만 명시적으로 제외.
3. `allow_secrets` 를 `allow_secret_filenames` / `allow_secret_contents` 로 분리.
   내용 스캔에서 나온 **고신뢰 패턴(private key, AKIA, ghp_, sk_live_)은 어떤 옵션으로도 우회 불가**로 두는 것을 권장.
4. 파일 수 상한에 걸리면 `report.warnings` 에 "N개만 검사했습니다"를 명시하고 UI에 노출.
5. 회귀 테스트 2개를 먼저 작성: 위 재현 케이스 1(통과하면 안 됨), 케이스 2(차단하면 안 됨).

---

## H2. credential helper 경로가 셸을 통과한다 — 공백이면 push 실패, 메타문자면 명령 실행

**위치:** `app/git/credentials.py:84-89`

```python
posix = Path(cred_path).resolve().as_posix()
return [("credential.helper", ""),
        ("credential.helper", f"store --file={posix}")]
```

git은 credential helper 문자열을 `use_shell=1` 로 실행한다. 공백/메타문자가 있으면 `sh -c` 를 거친다. 경로를 인용하지 않았다.

**교차검증 — 실제 git 2.43 으로 재현:**

```
# 공백 있는 경로
$ git -c credential.helper='store --file=/tmp/cred test dir/c.txt' credential fill
usage: git credential-store [<options>] <action>
fatal: could not read Username for 'https://github.com'   ← 인증 자체가 실패

# 메타문자 있는 경로
$ git -c 'credential.helper=store --file=/tmp/pwn$(touch /tmp/PWNED)dir/c.txt' credential fill
$ ls -la /tmp/PWNED
-rw-r--r-- 1 root root 0 Aug  6 20:13 /tmp/PWNED   ← 명령이 실행됨
```

**왜 아직 안 터졌나:** `tempfile.gettempdir()` 이 `%TEMP%` 를 따라가고, 네 계정 이름에 공백이 없기 때문이다.
Windows 계정 이름은 공백이 흔하다 (`C:\Users\Hong Gil Dong\AppData\Local\Temp\`).
**그런 PC에서는 push/pull/clone(private)이 100% 실패한다.** 이건 보안 이전에 배포 차단급 버그다.
주입 쪽은 `%TEMP%` 를 조작할 수 있는 상황이 전제라 실전 난도는 높지만, 인용 하나로 둘 다 사라진다.

**수정**

```python
posix = Path(cred_path).resolve().as_posix()
if any(c in posix for c in "'\"$`\\\n"):
    raise RuntimeError(f"임시 폴더 경로에 사용할 수 없는 문자가 있습니다: {posix}")
return [("credential.helper", ""),
        ("credential.helper", f"store --file='{posix}'")]   # 작은따옴표: $ 확장도 막힘
```

추가로 `write_credential_file` 에서 `dir=` 를 앱 전용 ASCII 경로(예: `%LOCALAPPDATA%\CloneUp\tmp`)로 고정하면 `%TEMP%` 의존이 사라진다.
테스트: 경로에 공백이 든 임시 디렉터리로 clone/push 를 돌리는 케이스 추가.

---

## H3. Git 설치 파일 서명 검증이 fail-open 이다

**위치:** `app/git/bootstrap.py:286-290`

```python
except Exception as e:
    # Soft: format OK but signature check failed to run
    return True, f"형식 확인 OK (서명 검사 생략: {e})"
```

PowerShell 실행이 실패하면 **검증을 건너뛰고 True 를 돌려주며, 호출부 `run_git_installer` 는 그대로 .exe 를 실행**한다.
PowerShell이 정책으로 막혔거나(ConstrainedLanguage), AV가 차단했거나, `powershell` 이 PATH에 없거나, 60초 타임아웃이면 발동한다.
즉 "검증 실패"와 "검증 통과"가 같은 결과다.

같은 함수의 두 번째 구멍: `if subject and not any(h in subj_l for h in hints)` — **subject가 빈 문자열이면 게시자 검사를 그냥 통과**한다.

세 번째: `"powershell"`, `"winget"`(bootstrap.py:132), `"clip"`(device_flow.py:213) 을 **절대경로 없이** 호출한다.
Windows `CreateProcess` 는 앱의 현재 디렉터리를 탐색 경로에 포함한다. 앱 CWD에 `powershell.exe` 를 심으면 서명 검증 결과 자체를 위조할 수 있다.

**수정**

1. 검증 실패·미실행 = 하드 실패. `except` 에서 `return False, ...` 로 바꾸고, 그 경우 브라우저 수동 설치로만 유도.
2. `subject` 가 비면 거부.
3. 절대경로 사용:
   `Path(os.environ["SystemRoot"], "System32", "WindowsPowerShell", "v1.0", "powershell.exe")`,
   `clip.exe` / `winget.exe` 도 `shutil.which()` 결과를 검증하거나 절대경로로.
4. 가능하면 GitHub Releases API 응답의 asset `digest` (sha256) 와 다운로드 파일 해시를 비교. 서명 검사보다 확실하다.
5. 그리고 이건 신뢰 문제인데 — **CloneUp-Setup.exe 자체는 서명이 없다** (`installer/CloneUp.iss` 에 SignTool 없음).
   사용자에게 "설치 파일 게시자를 확인한다"고 말하면서 자기 설치 파일은 SmartScreen 경고를 띄운다. 최소한 문서에 명시.

---

# P1

## M1. `run_git` 이 stdout 마스킹 결과를 버린다

`app/git/runner.py:108, 120` — `safe_out` 을 계산하고 반환값에는 원본 `out` 을 넣는다.

```python
safe_out = mask_secrets_in_text(out)      # 108: 계산
...
return GitResult(returncode=..., stdout=out, stderr=safe_err)   # 120: 안 씀
```

`sync_ops._git_detail(out)` 은 stdout+stderr 를 합쳐 그대로 다이얼로그에 뿌린다. 한 줄 수정: `stdout=safe_out`.

## M2. 토큰 누출 탐지 정규식 두 개가 서로 다르다

`app/git/publish.py:26-27` 의 `_TOKEN_LEAK_RE` 는 `gho_ | github_pat_ | x-access-token:` 만 본다.
**기본 로그인이 PAT(`ghp_`)인데 정작 `ghp_` 가 빠져 있다.** `ghs_`, `ghu_`, `ghr_` 도 없다.
`app/util/log_mask.py` 는 `gh[pousr]_` 로 제대로 잡는다 — 두 곳이 불일치한다.
`log_mask` 의 패턴을 공용 상수로 빼서 양쪽이 같은 것을 쓰게 한다. 40자 hex 구형 PAT 도 추가 검토.

## M4. 사용자가 고른 임의 폴더의 git 설정을 그대로 신뢰한다

「동기화」탭은 사용자가 지정한 폴더에서 `status / add / commit / pull / push` 를 돌린다.
그 폴더의 `.git/config` 와 `.git/hooks/` 는 **CloneUp 권한으로 코드를 실행시킬 수 있다**:
`core.fsmonitor`, `core.pager`, `diff.external`, `filter.*.clean`, `core.sshCommand`, `url.<x>.insteadOf`, `pre-commit` 훅.
압축파일로 받은 프로젝트를 초보가 그대로 물리는 게 이 앱의 주 사용 시나리오다.

`run_git` 에 안전 기본값을 항상 주입:
```python
SAFE_CFG = [("core.fsmonitor", ""), ("core.pager", "cat"),
            ("core.hooksPath", <빈 디렉터리>), ("core.sshCommand", "")]
```
그리고 commit 에 `--no-verify` 를 붙인다. (훅을 돌릴 이유가 없는 앱이다)

## M5. 요청 권한이 과하고, 기본 공개가 public 이다

- `app/config.py`: `DEFAULT_GITHUB_SCOPES = "repo"` — 사용자의 **모든** private 저장소 읽기/쓰기.
  첫 업로드 도구가 요구할 권한이 아니다.
- publish 기본이 `private=False`.

H1과 곱해지면 최악의 기본 경로가 된다: 불완전한 검사 → 통과 → **public** 저장소에 유출.

수정: 기본 `private=True`. 로그인 안내 1순위를 fine-grained PAT (대상 저장소 한정 + Contents: R/W)로.
classic PAT 을 쓰는 경우 기본을 `public_repo` 로 낮추고, private 저장소를 만들 때만 `repo` 를 요구.

## M6. 미서명 설치 파일 — H3 참고.

---

# P2

- **M3. sync 는 origin 호스트를 검증하지 않는다.** publish 는 `clone_url.startswith("https://github.com/")`, clone 은 호스트 화이트리스트가 있는데 `sync_ops.pull_repo`/`commit_and_push` 만 없다. `x-access-token` 문자열 검사만 한다. origin 호스트가 github.com 인지 확인하는 코드 3줄 추가.
- **L1.** `app/util/winproc.py:33` — `kw` 를 만들고 안 쓴다. 데드코드.
- **L2.** `_SECRET_NAME_RE` 의 `secret|credentials` 부분일치는 `docs/secrets.md` 같은 정상 파일을 잡는다 → H1의 "사용자가 검사를 끄게 만드는" 문제를 키운다.
- **L3.** `contextlib.redirect_stdout` 은 프로세스 전역이다. 워커가 둘 이상 겹치면 로그가 다른 창으로 새고 마스킹 전제가 깨진다. 워커별 로거로 교체.
- **L4.** Device Flow 차단이 환경변수 하나(`CLONEUP_ALLOW_DEVICE_FLOW=1`)다. 악성 프로세스가 세팅하면 그만이다. 릴리스 빌드에서는 코드 자체를 제외하는 게 맞다.
- **L5.** 재현 가능한 빌드가 없다. `PySide6>=6.6.0` 는 하한만 있고 lock/hash 고정이 없다. **테스트도 CI도 없다** (`tests/`, `.github/` 부재). 서명 없는 exe + 미고정 의존성 + 수동 빌드 = 공급망 관점에서 가장 약한 고리.
- **L6.** README 의 "토큰 저장: 이 PC OS keyring만" 은 보호처럼 읽히지만, Windows Credential Manager 항목은 같은 사용자로 도는 아무 프로세스나 읽는다. 한계를 정확히 쓰는 게 낫다.

---

# 실행 순서

**1단계 — 테스트 먼저 (반나절)**
`tests/` 생성. pytest 3개: (a) `.github/workflows` 안 AKIA 키가 차단되는가, (b) gitignore 된 `credentials.js` 가 통과되는가, (c) 공백 든 임시 경로로 credential helper 가 동작하는가. **지금은 셋 다 실패해야 정상이다.**

**2단계 — H2 (30분)**
`credentials.py` 인용 + 문자 검증. 테스트 (c) 통과 확인.

**3단계 — H3 (1시간)**
`verify_git_installer_file` fail-open 제거, 빈 subject 거부, powershell 절대경로. `winget`/`clip` 도 같이.

**4단계 — H1 (1~2일, 가장 큼)**
스캔 대상을 `git diff --cached --name-only -z` 로 전환 → 점 디렉터리 제외 제거 → `allow_secrets` 분리 → 파일 수 상한 경고 노출. 테스트 (a)(b) 통과 확인.

**5단계 — P1 묶음 (반나절)**
M1 한 줄, M2 정규식 통합, M4 안전 config 주입 + `--no-verify`, M5 기본값 private/scope 조정.

**6단계 — P2 + CI**
GitHub Actions 에 pytest + `pip-audit` + ruff. requirements 해시 고정. 설치 파일 서명 계획 수립(무료 대안이 없으면 README 에 미서명 명시).

---

## 잘 되어 있는 부분 (구체적 근거가 있는 것만)

칭찬이 아니라, **바꾸지 말라는 표시**다.

- 토큰이 argv 에 안 들어간다. `run_git` 의 주석과 구현이 일치하고, remote URL 은 항상 clean https 다.
- push 후 `.git/config` 와 `git remote -v` 를 재검사한다 — 사후 검증이지만 회귀 탐지에는 유효하다.
- `delete_credential_file` 이 unlink 전에 0으로 덮는다.
- `GIT_TERMINAL_PROMPT=0` + `GCM_INTERACTIVE=Never` 로 GUI 앱이 보이지 않는 프롬프트에 매달리는 걸 막는다.
- fine-grained PAT 의 빈 `X-OAuth-Scopes` 를 `repo` 로 추측하지 않고 `unknown` 으로 저장한다 (코드에 M3 회귀로 명시).
- Device Flow 를 공개 client_id 남용 이유로 기본 차단한 판단 자체는 맞다.
- `validate_branch_name` 의 leading-dash 거부 — argv 주입 인지가 되어 있다.
