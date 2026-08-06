# Org OAuth App 운영 가이드 (초보용 체크리스트)

CloneUp **브라우저 로그인(Device Flow)** 에 쓰는 GitHub OAuth App을  
**개인 계정**이 아니라 **Organization(조직)** 아래로 옮기거나, 처음부터 Org에 만드는 절차입니다.

- **코드 기능이 아닙니다.** GitHub 웹에서 하는 **운영 작업** + 설정 값 한 줄 교체입니다.
- **PAT 로그인**은 OAuth App을 거치지 않습니다. Org 이전과 별개로 이미 동작합니다.
- 제품 맥락: [DIFFERENTIATION.md](DIFFERENTIATION.md) V1 Trust.

---

## 1. 왜 하나?

| 지금(개인 앱) | Org 앱 |
|---------------|--------|
| 승인 화면: “○○(개인)의 앱” | “○○ 조직의 앱” |
| 만든 사람 계정에 종속 | 팀 멤버·인수인계 가능 |
| “취미/개인 앱” 인상 | “제품 앱”에 가깝게 보임 |

GitHub Desktop(공식) 수준 신뢰는 **되지 않습니다.**  
다만 “개인 취미” → “조직이 관리하는 제품” 으로는 한 단계 올라갑니다.

---

## 2. 준비물

1. GitHub 계정 (관리자)
2. (권장) 쓸 **Organization 이름** 정하기  
   - 예: `CloneUp-App`, `your-studio`  
   - 무료 Org로도 OAuth App 생성 가능 (요금제·정책은 GitHub 최신 문서 확인)
3. CloneUp 저장소 URL (OAuth App Homepage 로 씀)  
   - 기본: `https://github.com/seongbin45/CloneUp`
4. 배포 권한이 있는 PC (client_id 바꾼 뒤 Setup 다시 빌드)

**client_secret 은 데스크톱 앱에 넣지 않습니다.**  
Device Flow(public client)만 쓰면 됩니다.

---

## 3. Organization 만들기 (아직 없을 때)

1. 브라우저에서 GitHub 로그인
2. 오른쪽 위 프로필 → **Your organizations**  
   또는 https://github.com/settings/organizations
3. **New organization**
4. 플랜 선택 (개인 배포면 Free로 시작해도 됨)
5. Organization account name 입력 → 생성
6. (선택) Members에 공동 관리자 초대 (Owner 권한은 신중히)

---

## 4. Org 아래 OAuth App 만들기

1. Org 페이지 → **Settings**  
   (또는 https://github.com/organizations/ORG이름/settings/profile )
2. 왼쪽 **Developer settings** → **OAuth Apps**  
   - 개인 설정이 아니라 **Organization settings** 안이어야 함
3. **New OAuth App**
4. 예시 값:

| 필드 | 예시 |
|------|------|
| Application name | `CloneUp` |
| Homepage URL | `https://github.com/seongbin45/CloneUp` |
| Application description | (선택) Windows GitHub 도우미 — 로컬 폴더 업로드 |
| Authorization callback URL | Device Flow만 쓸 때도 GitHub이 URL을 요구하면 Homepage와 같게 넣거나 `http://127.0.0.1` 등 **쓰지 않는 자리**를 문서에 맞게 기입. **중요: secret을 앱에 넣지 말 것.** |

5. **Register application**
6. 생성된 **Client ID** 를 복사 (공개 가능,  nonetheless 남용 모니터링)
7. **Generate a new client secret** 은  
   - 서버형 앱이 아니면 **발급만 하고 데스크톱에 저장하지 않기**  
   - 또는 Device Flow only 이면 secret 없이도 되는 설정인지 현재 GitHub UI 확인

Device Flow 사용:

- OAuth App이 Device Authorization Grant 를 지원해야 합니다.
- CloneUp 코드 경로는 기존 `app/auth/device_flow.py` 그대로, **client_id 만 교체**.

---

## 5. CloneUp 설정 바꾸기

### 5-1. 코드 기본값 (배포용)

`app/config.py`:

```python
DEFAULT_GITHUB_CLIENT_ID = "새_Org_앱의_Client_ID"

DEFAULT_OAUTH_APP_OWNER_KIND = "organization"  # was: "personal"
DEFAULT_OAUTH_APP_OWNER_NAME = "당신_Org_이름"
DEFAULT_OAUTH_APP_HOMEPAGE = "https://github.com/seongbin45/CloneUp"
```

### 5-2. 로컬만 시험 (`.env`, 저장소에 커밋하지 말 것)

```env
GITHUB_CLIENT_ID=Ov23li...
GITHUB_OAUTH_APP_OWNER_KIND=organization
GITHUB_OAUTH_APP_OWNER_NAME=YourOrg
GITHUB_OAUTH_APP_HOMEPAGE=https://github.com/seongbin45/CloneUp
```

일반 사용자에게 `.env` 는 필요 없습니다. 배포 바이너리의 **기본값**이 중요합니다.

### 5-3. 앱에서 보이는 문구

로그인 방식 선택 창에 소유자(개인/조직)·scope·keyring 안내가 나옵니다.  
Org로 바꾼 뒤 `OWNER_KIND=organization` 이면 경고 문구가 “조직 「…」” 형태로 바뀝니다.

---

## 6. 검증 순서

1. 기존 로그인 **로그아웃** (상태줄 → 재로그인 흐름에서 로그아웃 또는 토큰 삭제)
2. 개발 실행: `.\.venv\Scripts\python.exe main.py`
3. **브라우저로 로그인** 선택
4. GitHub 승인 화면에 **Org 이름**이 보이는지 확인
5. 로그인 성공 → 상태줄에 계정 표시
6. (권장) PAT 로그인도 한 번 스모크 (회귀 없음 확인)
7. Setup 재빌드 후 설치본에서도 Device Flow 1회

---

## 7. 구(개인) OAuth App 정리

1. 새 Org 앱으로 배포가 퍼진 뒤 (예: 1–2주)
2. 개인 계정 → Settings → Developer settings → OAuth Apps
3. 옛 CloneUp 앱 → **Revoke all user tokens** (선택) / **Delete**
4. README·Release 노트에 “로그인 앱 이전, 한 번 재로그인 필요” 공지

옛 `client_id` 로 받은 토큰은 **새 앱과 호환되지 않습니다.**  
사용자는 재로그인이 필요합니다.

---

## 8. 운영 시 습관

| 주기 | 할 일 |
|------|--------|
| 앱 설정 변경 시 | Homepage·이름 일치, client_id 배포 동기화 |
| 멤버 변동 | Org Owner 2명 이상 권장 (한 사람 계정 잠김 대비) |
| 이상 트래픽 | GitHub OAuth App 사용량·권한 요청 모니터링 |
| 스코프 변경 | `DEFAULT_GITHUB_SCOPES` 와 승인 화면 문구 함께 검토 (`repo` 는 넓음) |
| 사용자 문의 | “불신이면 PAT” 안내 + 이 문서 링크 |

---

## 9. 하지 말 것

- client_secret 을 exe·Git·스크린샷에 넣기
- 개인 앱과 Org 앱 client_id 를 문서 없이 섞어 배포
- “GitHub 공식 앱”이라고 과장 표기
- Org 이전만으로 보안 감사·코드 사이닝이 끝났다고 착각

---

## 10. 체크리스트 (복붙)

```
[ ] Organization 생성
[ ] Org → OAuth App 등록, Client ID 복사
[ ] app/config.py DEFAULT_GITHUB_CLIENT_ID 교체
[ ] DEFAULT_OAUTH_APP_OWNER_KIND = organization
[ ] DEFAULT_OAUTH_APP_OWNER_NAME = Org 로그인 이름
[ ] DEFAULT_OAUTH_APP_HOMEPAGE 확인
[ ] 로그아웃 후 Device Flow 승인 화면에 Org 표시 확인
[ ] PAT 경로 회귀 확인
[ ] Setup 재빌드·Release 노트에 재로그인 안내
[ ] (나중) 개인 OAuth App 삭제
```

---

## 관련 코드

| 파일 | 역할 |
|------|------|
| `app/config.py` | client_id, owner kind/name, 신뢰 문구 |
| `app/ui/login_dialog.py` | 로그인 방식 + 소유 안내 |
| `app/ui/device_code_dialog.py` | 장치 코드 창 한 줄 고지 |
| `app/auth/device_flow.py` | Device Flow 프로토콜 (client_id 사용) |
| `app/auth/session.py` | PAT / Device 세션 |

질문이 “기능을 더 짜야 하나?” 라면: **대부분 아니오.**  
Org 만들고 client_id·메타데이터만 맞추면 됩니다.
