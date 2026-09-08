# Plan: CloneUp Update Manager — Tier 2 Persistent Pending Cache (rev. 9)

> **Status (2026-09-09):** Implementation landed in tree (paths/ACL/lock/pending/status/`run_once`/task migrate/iss Parallel+ACL/dialog 15s·15m poll + tests). **UM exe rebuild / Setup release still require explicit user approval.**

## Goal

Cross-tick resume + defer-safe zip + schtasks Parallel trigger with **correct UX** and **no status-file write races**.
---

## Decisions locked

| # | Topic | Decision |
|---|--------|----------|
| T2-1…T2-8, T2-1g…T2-1m | As rev.8 | Pending ACL, sticky, Parallel task, schtasks trigger, reparse=`os.rmdir` only, apply-gate full sha256. |
| **T2-1n** | **Status concurrency** | **Per-run files + atomic current pointer** (option 1). Never have two processes rewrite one shared `last_run.json`. |
| **T2-1o** | **Start-wait window** | Dialog waits **15 seconds** for a new `run_id` to appear after `/Run`. Then enter result-poll (extend to **15 minutes** while pid alive + downloading). Neutral copy if no new run: 「확인 요청을 보냈지만 응답이 없습니다」. |

---

## Status layout (T2-1n)

```
{status_root}/
  current.json          # {"run_id":"…"}  — only updated via os.replace from a temp file
  runs/
    {run_id}.json       # full status for that run; writer = that process only
```

### Writer rules (`run_once`)

1. Generate `run_id` at start.  
2. Write `runs/{run_id}.json` (own file only).  
3. Atomically publish pointer: write temp → `os.replace` → `current.json`.  
4. Progress updates: only touch **own** `runs/{run_id}.json`.  
5. If `PendingLock` not acquired: write own run file with `phase=pending_busy` + `finished_at`, publish `current.json` to that run_id, exit. (Parallel instance can always start and signal busy.)  
6. Never open another run’s JSON for write.

### Dialog poll

```
snap = read current.json run_id (may be null)
trigger /Run
wait ≤15s until current.run_id != snap (new run)
  else → neutral timeout message
poll runs/{new_run_id}.json until finished / pid dead / 15m cap while alive
```

ACL: same as before — Users **Read** on status tree; SYSTEM/Admin **Write** (machine).

---

## Why not shared last_run.json

With **Parallel**, a busy worker and a manual trigger both run. A single file allows last-writer-wins corruption of the click’s result. Per-run files + atomic `current.json` preserve run identity under concurrency.

---

## Modules / order

1. paths + ACL + sticky + status_root  
2. pending.py + status writer (per-run + current)  
3. run_once  
4. try_start_manager schtasks + dialog poll (15s / 15m rules)  
5. task SD + **MultipleInstances=Parallel** migration + iss  
6. tests (busy overwrite race, run identity, pid death, sticky, ACL)  
7. docs; no build until asked  

## Non-goals

- Metered throttle; Session-0 GUI; Users-writable pending content  

---

## Rev. 9 addenda (approved review)

### T2-6b — Status runs prune

On each `run_once` end (any terminal phase), prune `status/runs/`:

- Keep at most **K = 48** newest run JSON files (≈2 days of hourly ticks), **or**
- Delete files with `finished_at` / mtime older than **N = 7 days**

Whichever is more aggressive may both apply: first delete by age, then if count > 48 trim oldest. Never delete the file pointed to by `current.json` until a newer current exists.

### T2-1o′ — After 15-minute poll cap

If pid is still alive and phase is `running` / `downloading` when the 15m dialog poll cap is hit:

- Dialog may **close** with copy: 「백그라운드에서 계속 확인 중입니다. 끝나면 알림으로 알려 드립니다.」
- UM continues; on terminal phase, tray (or next dialog open) can show result via `current.json` / run file.
- Do **not** show a hard failure for a live download.

