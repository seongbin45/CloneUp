# Home scan cost baseline & heavy-root (rev. 7.1)

Script: `scripts/bench_home_scan.py`  
Machine (this doc): Windows, user `seong`, CloneUp repo host PC.

## Locked constants (rev. 7.1)

| Constant | Value | Meaning |
|----------|------:|---------|
| `DIRTY_ENRICH_CAP` (K) | **8** | Initial dirty enrich budget |
| `DIRTY_TTL_SEC` | **90** | Re-probe TTL |
| `DIRTY_SELECT_DEBOUNCE_MS` | **300** | Selection debounce |
| `DEFAULT_SEED_MAX_DEPTH` | **2** | Depth when walking heavy/seed roots |
| `HEAVY_CHILD_THRESHOLD` (T) | **48** | B-layer: direct children ≥ T → heavy |
| `HEAVY_CHILD_SCAN_LIMIT` | **48** | scandir early-exit (=T, intentional) |
| Pass A pin budget | **`MAX_RECENT`** (settings, currently **12**) | No separate pin constant |

### Heavy = A ∪ B

| Layer | Rule |
|-------|------|
| **A** | `SHGetKnownFolderPath`: Profile, Desktop, Documents, Downloads. Compare with `resolve()` + `os.path.normcase`. Session-once cache. **Fail-closed:** any required FOLDERID failure → all paths heavy for the session (+ DEBUG log). |
| **B** | Paths not in A: `count_direct_children ≥ T`. |

**Not used for A:** `Path.home()` / `~/Desktop` string hardcodes.

### Behavior contract

| Situation | light | heavy |
|-----------|-------|-------|
| Adopt recent’s **parent** as walk root | yes | **no** |
| Hybrid **seed** walk | — | yes, seed depth |
| Registered `scan_roots` | walk, normal depth | walk, **seed depth** |
| Pass A recent pin | up to `MAX_RECENT` | pin regardless of heavy |
| A-layer fail-closed | — | treat **all** as heavy (no parent adopt) |

### Limits / Non-goals

- **8.3 short names:** not covered by resolve+normcase (R-10).
- **UNC Desktop:** API may succeed with UNC path — judgment OK, walk cost **unmeasured** (R-8).
- **macOS / iCloud:** out of scope (Windows app).
- **rev.8 candidates:** walk time-box, path-key cache, GetLongPathName, UNC bench.

### Ops checklist (R-9, no telemetry)

If reports repeat: “sibling projects missing on home” or “home list huge/slow without scan roots” → re-run S0b child-count table and reconsider T. If DEBUG shows A-layer fail-closed, fix Known Folder / profile first (not T).

---

## S0 — pre-allowlist baseline (2026-09-09)

| Metric | Value |
|--------|------:|
| `n_roots` | 16 (incl. Desktop, Documents, source, Downloads) |
| `phase1_ms` | 842 |
| `n_projects` / `n_git` | 46 / 29 |
| `enrich_all_ms` | 9517 |

## S0b — child counts (2026-09-09, this PC)

| Path | n | role |
|------|--:|------|
| Profile/home | 89 | A |
| Desktop | 45 | A |
| Documents | 41 | A |
| Downloads | 335 | A |
| `Desktop\ProJect` | 25 | B light want |
| CODYSSEY_6 / visitholykorea | 29 / 33 | B light want |
| `Downloads\scpc2026_work` | 48 | B heavy start → **T=48** |
| AppData\Roaming / Local | 58 / 112 | B heavy |

T=48 = **sibling-discovery priority** over “ambiguous→strict” for the empty 34–47 sample gap on this PC. Single-machine; not claimed as global optimum.

## Post-allowlist baseline (pre–rev.7.1 code)

| Field | Value |
|-------|-------|
| **Date** | 2026-09-09 |
| **Machine** | `seong` Windows CloneUp host |
| **Protocol** | single-shot then later N=3 median for S0c |
| **Case A** `phase1_ms` | **~40 ms** (recorded 39.9 / 46) |
| `n_roots` | 12 |
| `n_projects` / `n_git` | 24 / 20 |

Use this row when judging **3× outlier** after rev.7.1: if phase1 ≫ 120 ms, check whether `n_roots` / walk set changed (behavior change) vs pure regression.

## S0c — after rev.7.1 (2026-09-09, same PC)

Protocol: warm once, then **N=3 median**. OS cache: warm.

| Case | n_roots | phase1_ms (median) | heavy_check_ms | n_heavy_checks | notes |
|------|--------:|-------------------:|---------------:|---------------:|-------|
| A recent, roots empty | 12 | **41.4** | 5.94 | 24 | vs pre-7.1 ~40ms — not 3× |
| C ≥5 registered roots | 5 | **30.9** | 1.82 | 5 | temporary save_scan_roots |

**C5:** Case A 41.4 ms vs prior ~40 ms baseline row — OK (no 3× outlier). If investigating a future spike, ask first whether `n_roots` / walk set changed (behavior) vs pure slowdown.

**C6 observes (after session-once A-set):** per-check cost ≈ `resolve()` (+ junction expand) + `normcase` + set lookup + (if not A) scandir up to T. Not repeated Known Folder API calls.

---

## Implementation tracking

- Plan **rev.7.1** approved → implement Docs → code → tests → S0c → verify
`}