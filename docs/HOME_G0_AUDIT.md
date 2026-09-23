# G0 — Home “Already done” audit (rev. 3)

Date: 2026-09-09 · Repo: CloneUp · Commands: plan G0.1–G0.6 kit

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Light home tokens (5) | **❌ → P1** | `theme.LIGHT` has `#fbfaf8`, `#1f6f5c`. **Missing** `#f0ede6`, `#f6f4ef`. Text is `#2f2b24` not `#232019` (`#232019` only on `DARK.bg_window`). |
| 2 | Timeline buckets | **✅** | `home_shell.py` imports/uses `group_by_time_bucket` (~L38, ~L726) |
| 3 | Row expand | **✅** | `_toggle_expand` + `list_recent_child_paths` (`home_shell.py` ~L39, 841, 942, 946) |
| 4 | Overflow ⋯ | **✅** | `make_overflow_button` / `populate_overflow_menu` / `_show_overflow` (`home_shell` + `home_chrome`) |
| 5 | GitMissingBanner | **✅** | `home_chrome.GitMissingBanner`; wired in `home_shell` / `main_window`. Copy ≈ design (P3 may polish). |
| 6 | `time_bucket_label` | **✅** | `project_scan.py`: 오늘 / 어제 / 이번 주 / 지난주 / 더 오래 전 (`_BUCKET_ORDER`) |

**Gate:** G0 closed. P1 must close token gaps before relying on “시안 색 = theme.LIGHT”.
