# Cross-verify: Home Phase C (2026-09-09)

## Checks

| Check | Result |
|-------|--------|
| Unit tests (`test_project_scan`, home shell/chrome) | **9 passed** |
| `verify_settings_menu_crosscheck.py` | **SETTINGS_MENU_CROSS_VERIFY_OK** |
| `scripts/verify_home_phase_c.py` | **HOME_PHASE_C_VERIFY_OK** (13 PASS) |
| Live load (fast scan) | **46 entries** in ~1–2s |
| Expand twisty | **PASS** — caption + 8 sub paths |
| Timeline buckets | **PASS** — 오늘/어제/이번 주/지난주/더 오래 전 |
| Dirty column | porcelain → `파일 N개` when probed |

## Issue found & fixed during verify

Initial scan used `probe_dirty=True` for every git repo (~**18s** on this PC). Desktop smoke waited 8s → **entries=0** (worker still running).

**Fix:** fast scan (`probe_dirty=False`) then background `_DirtyEnrichWorker` fills dirty/branch/counts.

## How to re-run

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_project_scan.py tests/test_home_shell_phase_b.py tests/test_home_chrome_phase_a.py -q
.\.venv\Scripts\python.exe scripts\verify_home_phase_c.py
.\.venv\Scripts\python.exe scripts\verify_settings_menu_crosscheck.py
```
