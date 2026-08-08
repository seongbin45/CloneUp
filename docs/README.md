# `docs/` — 설계·검증·운영 문서

코드보다 **긴 설명·표·체크리스트**를 둡니다.

## 색인

| 문서 | 내용 |
|------|------|
| [UX_GUIDANCE.md](UX_GUIDANCE.md) | 초심자 안내 4층 (팁 카드, G3 확인, 「다음:」) |
| [DIFFERENTIATION.md](DIFFERENTIATION.md) | GitHub Desktop·Bitbucket 대비 **차별 가치**와 로드맵 |
| [ORG_OAUTH_APP.md](ORG_OAUTH_APP.md) | **Org OAuth App 운영** 초보 체크리스트 (client_id 이전) |
| [RELEASE_0.1.6.md](RELEASE_0.1.6.md) | **0.1.6** 사용자·배포 노트 (현재) |
| [RELEASE_0.1.5.md](RELEASE_0.1.5.md) | **0.1.5** 사용자·배포 노트 |
| [RELEASE_0.1.4.md](RELEASE_0.1.4.md) | **0.1.4** 사용자·배포 노트 |
| [RELEASE_0.1.3.md](RELEASE_0.1.3.md) | **0.1.3** 사용자·배포 노트 |
| [RELEASE_0.1.2.md](RELEASE_0.1.2.md) | **0.1.2** 사용자·배포 노트 |
| [RELEASE_0.1.1.md](RELEASE_0.1.1.md) | **0.1.1** 사용자·배포 노트 |
| [PACKAGING.md](PACKAGING.md) | exe / Setup 빌드 |
| [POWERSHELL_BUILD_SCRIPTS.md](POWERSHELL_BUILD_SCRIPTS.md) | **`.ps1` 빌드 스크립트 초심자 설명** (exe 만들기 전) |
| [GIT_BOOTSTRAP.md](GIT_BOOTSTRAP.md) | Git 없을 때 설치 도우미 (D방식) |
| [FAILURE_CASES.md](FAILURE_CASES.md) | 실패 시나리오 체크리스트 |
| [PII_CROSS_VERIFY.md](PII_CROSS_VERIFY.md) | 비밀파일·개인정보 스캔 교차검증 |
| [SECURITY_CROSS_VERIFY.md](SECURITY_CROSS_VERIFY.md) | **보안 전면 교차검증** + `scripts/verify_security_crosscheck.py` |
| [ICON_CROSS_VERIFY.md](ICON_CROSS_VERIFY.md) | 아이콘 시안 대조 |
| [DESIGN_PHASES.md](DESIGN_PHASES.md) | UI 디자인 단계 |
| [PLAYWRIGHT_DEVICE_FLOW.md](PLAYWRIGHT_DEVICE_FLOW.md) | 실험용 Playwright 로그인 |
| [UI_PUBLISH_SKELETON.md](UI_PUBLISH_SKELETON.md) | 초기 Publish UI 메모 |

## 초심자: 변경·배포 절차는?

**짧은 실무 절차는 저장소 루트 [README.md](../README.md)** 에 모았습니다.  
(개발 환경 → 커밋 → 병합 → Setup 빌드 → 사용자 전달)

이 폴더 문서는 “왜 이렇게 만들었는지 / 검증 표”용입니다.

## 문서만 수정했을 때

```powershell
git add docs/
git commit -m "docs: 설명 보강"
git push
```

Setup 재빌드는 **필요 없습니다** (문서만 바뀐 경우).
