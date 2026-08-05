# 실험: Playwright Device Flow 보조

**기본 로그인은 수동 Device Flow입니다.**  
Playwright는 **옵트인 실험**이며, 실패하면 클립보드 + 일반 브라우저로 폴백합니다.

## zip 스냅샷에서 확인한 페이지

파일: `github.com/login/device/select_account.html` (제공된 `github.com.zip`)

| 항목 | 내용 |
|------|------|
| 제목 | Device Activation |
| 역할 | **계정 선택** (코드 입력 페이지 아님) |
| 로그인 표시 | Signed in as **seongbin45** |
| 진행 버튼 | `<input type="submit" class="btn btn-sm btn-primary" value="Continue" aria-label="Continue as seongbin45">` |
| 다른 계정 | `/login?add_account=1&…` 링크 |

코드 입력 폼은 이 zip에 없었습니다. Playwright 모듈은 이후 화면의 `user_code` 입력란을 **여러 셀렉터로 추정**합니다.

## 활성화

```powershell
cd C:\Users\seong\Desktop\ProJect\Codyssey_2+1_ProJect\CloneUp
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium

$env:CLONEUP_PLAYWRIGHT = "1"
.\.venv\Scripts\python.exe main.py
# 또는
.\.venv\Scripts\python.exe spike_device_flow.py --force
```

끄기:

```powershell
Remove-Item Env:CLONEUP_PLAYWRIGHT -ErrorAction SilentlyContinue
```

## 동작 순서

1. Device code 발급 + 클립보드 복사 (기존과 동일)  
2. `CLONEUP_PLAYWRIGHT=1` 이면 Chromium 실행  
3. `/login/device` (또는 `?user_code=`) 이동  
4. **select_account**: `Continue` 클릭 (스냅샷 셀렉터)  
5. 코드 입력란이 보이면 `user_code` 입력·제출  
6. Authorize 버튼이 보이면 클릭 시도  
7. passkey/추가 확인은 사용자가 브라우저에서 완료  
8. 앱은 기존처럼 토큰 폴링  

## 한계

- GitHub UI 변경 시 깨짐  
- passkey / 2FA / CAPTCHA 는 자동화 불가할 수 있음  
- 배포 exe에 Playwright를 기본 포함하지 않는 것을 권장  
