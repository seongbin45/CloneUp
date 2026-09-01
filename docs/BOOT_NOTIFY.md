# 시작 알림 (안 올린 수정)

시안: `desin/CloneUp 시작 알림.dc.html`

## 무엇을 하나요

컴퓨터에 로그인한 뒤(또는 `CloneUp.exe --tray`), 최근 폴더에  
**GitHub로 안 보낸 변경**이 있으면 우하단 토스트로 묻습니다.

- 제목: **안 올린 수정이 있어요**
- 변경 파일 미리보기 · 여러 폴더는 한 알림에서 고르기
- **이 알림 그만 받기** → 일주일 쉬기(권장) / 아예 끄기
- 알림에서 올려도 **비밀 파일 점검은 그대로** — 걸리면 앱 창을 엽니다

## 켜는 법

1. **설정 → 안전**
   - 「켤 때 안 올린 수정 확인」 ON
   - 「Windows 시작 시 트레이에서 대기」 ON (시작 프로그램 등록)
   - 앱 기동·설정 열 때 **선호값 ↔ HKCU Run(`CloneUpTray`)을 맞춤**  
     (선호 ON인데 등록 실패 시 토글은 OFF로 되돌림)
2. 또는 개발 중:
   ```powershell
   .\.venv\Scripts\python.exe main.py --tray
   ```

## 규칙

- 변경이 없으면 알림 없음
- 같은 날 두 번 이상 묻지 않음
- 「나중에」→ 다음 부팅에 다시
- 폴더 알림 폭탄 없음 (recent 목록을 한 토스트로)

## 코드

| 모듈 | 역할 |
|------|------|
| `app/ui/boot_scan.py` | recent 스캔 · porcelain · snooze |
| `app/ui/boot_notify.py` | 토스트 UI |
| `app/ui/tray_app.py` | 트레이 · 업로드 워커 |
| `app/util/autostart_win.py` | HKCU Run 등록 |
| `main.py --tray` | 트레이 전용 기동 · 단일 인스턴스 |
