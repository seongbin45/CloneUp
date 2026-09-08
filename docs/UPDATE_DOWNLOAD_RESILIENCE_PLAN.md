# Plan: CloneUp Update Download — Industry-Parity Resilience (rev. 3)

## Decisions locked (before / during Tier 1 impl)

| # | Topic | Decision |
|---|--------|----------|
| 1 | Attempt nesting | **No nesting.** Tier 0’s “3 full-file retries” is **replaced** by one loop: `_DOWNLOAD_MAX_ATTEMPTS = 8` inside `download_asset` (resume-aware). Worst case is 8 attempts, not 8×3. |
| 2 | Tier 2 lock | Prefer **OS exclusive handle** on `download.lock` (process death releases the handle). Optional PID stale-check only as secondary. (Implemented in Tier 2, not Tier 1.) |
| 3 | Last-Modified | Allowed as `If-Range` fallback with **warning**; hot-redeploy collision risk remains if **no ETag and no digest**. Mitigated by fail-closed digest (below). |
| 4 | Digest survey | **Last 5 zip-bearing releases** (v0.1.9–v0.1.13, surveyed 2026-09-09) **all** have `sha256:` digest → **`_REQUIRE_DIGEST = True`** (fail-closed if API omits digest). |
| 5 | ENOSPC | Burns attempt budget until hard fail; do not imply space will magically free. |
| 6 | `os.replace` | Retry with short backoff on `PermissionError` (Windows AV lock). |

**Tier 1 status:** implemented in `update_manager/apply.py` (intra-call only).

---

## Goal

Bring CloneUp Update Manager downloads up to **industry-comparable practice** for large HTTPS assets (~200MB+ GitHub Release zips):

- Survive stalls and drops without restarting from byte 0 every time (where the design actually retains bytes)
- Never treat a partial file as a successful download
- Detect “same URL, different bytes” across resume attempts (ETag / If-Range)
- Keep automatic GitHub issue spam for transient network noise under control (already partly done)
- Stay dependency-light (PyInstaller onefile UM) — **urllib only**

**Final bar (parity with HF Hub / pip / yt-dlp / electron-updater patterns):**

| Capability | Status now | Target tier |
|------------|------------|-------------|
| Whole-file retry + longer timeout | Absorbed into Tier 1 attempt loop | 0→1 |
| Soft vs hard diag (SSL / timeout) | Done | 0 (keep) |
| HTTP Range resume + 206/200 check | **Done (Tier 1)** | 1 |
| ETag / If-Range on resume | **Done (Tier 1)** | 1 |
| `.part` + atomic complete | **Done (Tier 1)** | 1 |
| Size check + digest when present | **Done; digest required** | 1 |
| Digest fail-closed policy | **Done** (5/5 recent zips) | 1b done early |
| Persistent pending across ticks / defer | Missing (temp dir) | **2** |
| Single-writer lock on pending | Missing | **2** |
| Payload shrink / zip-slip / UX polish | Later | **3–4** |

---

## Honest scope: what “resume” means in each tier

### Tier 1 = **intra-call resume only** (must say this out loud)

`run_once` still uses `TemporaryDirectory`. So:

- `.part` lives **inside that temp tree** for one `download_asset` / one staging attempt.
- Tier 1 helps when: **one tick** hits read timeout / connection drop mid-stream and the **retry loop inside `download_asset`** continues with `Range`.
- Tier 1 does **not** help when: tick ends, process restarts, UI defer returns early and temp is wiped, or the next hourly tick starts a new temp dir.

**Shipping Tier 1 alone must not be marketed as “업데이트 이어받기”.**  
User-facing / release notes should say: *같은 다운로드 시도 안에서 끊기면 이어서 받음. 다음 주기·앱 재시작 이후 이어받기는 Tier 2.*

Cross-tick resume is **explicitly Tier 2** (persistent `%LOCALAPPDATA%\...\pending\`).

---

## Current architecture (constraints)

```
run_once
  → TemporaryDirectory(cloneup_upd_*)
  → stage_zip_update → download_asset → extractall → find onedir
  → if main window visible → defer (temp wiped → all progress lost)
  → else kill CloneUp → copy_onedir_into
```

---

## Tier 0 — Survival kit — **DONE** (`80ef5a1`)

- Timeout 900s, 3 full-file retries, backoff
- Soft-diag for SSL / timed-out apply while running
- Supersede apply failures after later `success`

Needs **UM rebuild** to reach installed PCs.

---

## Tier 1 — Intra-call Range resume (NEXT)

Industry analogue: HF `http_get`, pip resume-retries, yt-dlp Range + Content-Range.

### Behavior

```
download_asset(url, dest, digest=None)
  part = dest + ".part"
  meta sidecar optional: dest + ".part.meta"  # etag, expected_total, url fingerprint
  attempts = 0
  while attempts < MAX_ATTEMPTS:          # hard cap (e.g. 8), includes resume tries
    attempts += 1
    resume_from = size(part) if part.exists() else 0
    headers = {}
    if resume_from > 0:
      headers["Range"] = f"bytes={resume_from}-"
      if saved_etag: headers["If-Range"] = saved_etag
    resp = urlopen(...)
    status = resp.status

    # --- Range / identity handling ---
    if resume_from > 0:
      if status == 200:
        # CDN ignored Range OR If-Range failed (resource changed) → restart clean
        truncate part; resume_from = 0; clear etag; rewrite from 0
      elif status == 206:
        parse Content-Range; if present, require start == resume_from
        if Content-Range missing: treat as unsafe → truncate + restart from 0
          (or: accept only if Content-Length + resume math is unambiguous — default = restart)
      elif status == 416:
        # already complete or bogus size → validate size vs expected / restart
      else:
        error → retry after backoff (leave .part)

    if resume_from == 0 and status == 200:
      save ETag / Last-Modified from response into .part.meta
      open part wb
    elif status == 206:
      open part ab

    stream chunks into part; on TimeoutError/OSError/URLError:
      leave .part + meta; backoff; continue loop

  # --- completion ---
  require expected_total if known (from first Content-Length or Content-Range total)
  if size(part) != expected_total when known → fail, keep or delete .part per policy
  sha256(part); if digest provided and mismatch → delete part+meta, raise
  os.replace(part, dest); delete meta
```

### Explicit rules from review

1. **ETag / If-Range (required in Tier 1)**  
   - On first full response (200), store `ETag` (prefer) or `Last-Modified`.  
   - On resume, send `If-Range`.  
   - If server returns **200** after If-Range → resource changed or Range unsupported → **truncate and restart** (never append).  
   - If no ETag/Last-Modified from server → still allow Range resume but log warning; rely on final digest when present, else size-only.

2. **206 without Content-Range**  
   - Default: **unsafe → truncate + full restart** (yt-dlp-level paranoia). Document in code comment.

3. **Attempt budget**  
   - `MAX_ATTEMPTS = 8` (or similar) for the whole `download_asset` call (not infinite resume loop).  
   - Optional: also abort if `attempts >= 3` with **zero byte progress** since last successful read.

4. **Digest / integrity policy (Tier 1 vs 1b)**  
   - **Tier 1:** always verify size when total known; verify digest **when GitHub sends `digest`**.  
   - **Tier 1b (before calling it “parity”):** measure N recent CloneUp releases (and GitHub API behavior) for `assets[].digest` presence.  
     - If digest present on **all** last K releases → switch to **fail-closed** (refuse download apply without digest).  
     - Until then, log `integrity=size-only` and do not claim bit-level integrity.  
   - Plan must not leave fail-closed as endless “later”: **acceptance gate = scripted check on latest release + previous 5 tags**.

5. **Test wording (clarified)**  
   - Digest mismatch: **final `dest` must not exist**; **delete `.part` (and meta)** on mismatch so a bad partial is not reused.  
   - Do not say “delete dest” when dest was never published.

6. **Disk space (Tier 1 minimum)**  
   - Before starting (or before first write), if `expected_total` known, check free space on `dest`’s volume (`shutil.disk_usage`); if free < expected_total + small margin → fail fast with clear error, no orphan `.part` growth.  
   - Mid-download `ENOSPC` → leave `.part`, raise; next attempt may resume if space freed.

### Out of scope for Tier 1

- Surviving across ticks / defer / process restart (**Tier 2**)
- Cross-process lock (**Tier 2**)
- Build/release

---

## Tier 2 — Persistent pending + single-writer — **IMPLEMENTED** (see `UPDATE_TIER2_PENDING_PLAN.md` rev.9)

```
%PROGRAMDATA%\CloneUp\UpdateManager\pending\{version}\   # machine mode
%LOCALAPPDATA%\CloneUp\UpdateManager\pending\{version}\  # user mode
  CloneUp-win64.zip / .part / .part.meta
  meta.json
  download.lock                 # OS exclusive (PendingLock)
  extract\ + .complete

%PROGRAMDATA|LOCALAPPDATA%\CloneUp\UpdateManager\status\
  current.json                  # atomic pointer
  runs\{run_id}.json            # per-run (Parallel-safe)
```

- Staging root = pending (sticky choice) → **cross-tick resume**
- Idle cache skip re-download; **apply-gate always full sha256**
- Defer when main window visible → keep zip; skip kill/copy only
- Version prune; junction-safe remove (`os.rmdir` not rmtree-through)
- Machine pending ACL: SYSTEM+Admins write (no Users) — anti-LPE
- schtasks **Parallel** + interactive `/Run`; dialog poll 15s / 15m
- **No UM rebuild until user asks** (code+tests landed; field effect needs build)
---

## Tier 3–4 — Hardening / product

- Fail-closed digest after Tier 1b gate
- Connect vs read timeout split; progress heartbeat
- Structured log fields: `resumed_from`, `attempt`, `bytes`, `etag`
- Zip-slip sanitize; optional payload shrink
- Docs + release notes; UM rebuild for field effect

---

## Implementation order

1. Revise plan with limits + ETag + digest gate — done
2. Implement **Tier 1 only** (`apply.py` + tests) — done (`bc1cd45`)
3. Tier 1b digest fail-closed — done (5/5 zips)
4. **Tier 2** pending + status + schtasks Parallel + dialog poll — **code done** (await UM rebuild)
5. **No UM build** until user asks
## Success criteria

**Tier 1**

- Unit tests: resume 206, 200-on-Range truncate, If-Range→200 restart, 206 w/o Content-Range restart, digest mismatch deletes `.part`, attempt cap, disk check when total known
- Docs/comments state **intra-call only**
- CI green when pushed

**“Industry parity” claim**

- Only after Tier 1 + Tier 2 + Tier 1b fail-closed (or documented exception if GitHub digest coverage &lt; threshold)

## Non-goals now

- Shipping Setup/UM binaries without explicit approval
- SYSTEM vs user UM security redesign (separate track)
