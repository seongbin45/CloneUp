# Research: How industry & academia cut local filesystem scan cost

**Question:** When loading “what’s on the user’s PC” is slow/inefficient, how have representative systems reduced **time** and **resource cost** with data structures and algorithms?

**Scope:** Local (or HPC parallel FS) **enumeration / discovery / change detection** — not cloud object storage as the primary topic.  
**Bar for sources:** Systems that define a whole class (OS search, Git, Watchman, USENIX FAST), or widely measured open implementations — not one-off blog tips.

**Date:** 2026-09-09

---

## 1. The cost model (why naive walks hurt)

A recursive “list every folder under Desktop” pays roughly:

| Cost | What happens |
|------|----------------|
| **I/O amplification** | One `readdir`/`FindFirstFile` per directory + often `stat`/`GetFileAttributes` per entry |
| **Syscall / HANDLE tax** | On Windows, metadata often needs a full HANDLE; antivirus can multiply cost |
| **CPU** | Ignore-rule matching, path string work, UI marshaling |
| **Latency to first paint** | User waits until the whole walk finishes if the UI is synchronous |

**Key insight shared across successful systems:**  
Do **not** re-discover the whole tree on every query. Separate:

1. **Initial census** (once, or rarely)  
2. **Incremental update** (cheap)  
3. **Selective deep work** (only for paths that matter)  
4. **Presentation** (virtualize / progressive UI)

Git’s own analysis frames `status` as validating a **cached model** against a mutable FS — not “just looking at files” ([High Performance Git, Ch.7](https://gitperf.com/chapter-07.html)).

---

## 2. Taxonomy of mitigation strategies

```
A. Avoid walking the tree at all
   A1. Read volume metadata bulk (MFT / catalog)
   A2. Read OS change journals (USN / FSEvents / inotify)

B. Walk less
   B1. Depth / breadth caps, root allowlists
   B2. Skip sets (.git, node_modules, …)
   B3. Stop at project roots (don’t descend into repos)

C. Walk smarter
   C1. Parallel / work-stealing tree walk (HPC)
   C2. Proximity-aware scheduling
   C3. Cache directory mtimes (untracked cache)

D. Don’t walk again
   D1. Persistent index (Everything, Spotlight, Windows Search)
   D2. FS monitor daemon (Watchman, git fsmonitor)
   D3. Two-phase: fast list → background enrich

E. Cost-shift presentation
   E1. Virtualized lists / progressive reveal
   E2. Debounce / coalesce change events
   E3. Content search only after name filter (Everything content:)
```

---

## 3. Class A — Bypass recursive crawl (volume metadata)

### 3.1 Everything / NTFS MFT + USN (consumer desktop search)

**Representative system:** voidtools **Everything** (widely used Windows name search since ~2009).

| Phase | Mechanism | Cost tradeoff |
|-------|-----------|----------------|
| Build index | Read **NTFS Master File Table (MFT)** names/locations — not recursive Win32 crawl | Seconds for hundreds of thousands of files; RAM ~tens of MB for ~250k files ([FAQ](https://www.voidtools.com/faq/)) |
| Stay fresh | **USN Change Journal** maintained by NTFS driver | O(changes), not O(files); missed only if journal truncated → full reindex ([forum / developer](https://www.voidtools.com/forum/viewtopic.php?t=12371)) |
| Query | In-memory name DB | Instant name search; **content** search intentionally slow (opens files) |

**Algorithmic idea:** Treat the volume’s own directory of records as the ground truth for **names**, and the journal as a **delta log**.

Open-source mirrors of the same idea: MFTIndexer, PulseFS, FastFileSearch, `ntfs-reader` (Rust) — all document MFT bulk enum + USN for updates ([PulseFS claims ~836k files &lt; 2s for name index](https://github.com/ahmetburakcoskun/PulseFS)).

**Security / cost note:** Raw volume access (`\\.\C:`) typically needs elevation; journal size must be large enough or clients fall back to full reindex ([Everything USN size guidance](https://www.voidtools.com/forum/viewtopic.php?t=14153)).

### 3.2 Academic / FS design: full-path indexing

**USENIX FAST’18 — “The Full Path to Full-Path Indexing”** (Zhan et al., ArborFS/BetrFS line): show that write-optimized dictionaries + range-rename can make **recursive greps ~1.5× faster** while keeping renames competitive ([FAST 18](https://www.usenix.org/conference/fast18/presentation/zhan)).  
**Takeaway for app authors:** If the store indexes by full path, directory scans become range queries — but rename complexity moves into the KV layer.

### 3.3 HPC: parallel tree walk

**SC 2012 — “On distributed file tree walk of parallel file systems”**: randomized **work-stealing**, proximity-aware, and hybrid schedulers for huge PFS trees — orders of magnitude faster than serial tools on LANL production FS ([IEEE SC 2012](https://www.computer.org/csdl/proceedings-article/sc/2012/1000a015/12OmNy49sLM)).  
**Takeaway:** When you *must* walk, parallelize work distribution; don’t assume one thread + DFS.

---

## 4. Class B — Walk less (policy & pruning)

Used by almost every practical tool (find, IDEs, CloneUp home scan):

| Technique | Effect |
|-----------|--------|
| **maxdepth** | Bounds worst-case directories visited |
| **Skip lists** | Avoid dense junk (`node_modules`, `.git` internals, build outs) |
| **Stop at project root** | Once `.git` found, don’t descend (CloneUp `project_scan` does this) |
| **Root allowlist** | Index only registered “찾을 위치” / project roots — never whole disk by default |
| **Watchman `root_restrict_files`** | Org policy: only watch true project roots to avoid overlapping watches ([Watchman troubleshooting](https://facebook.github.io/watchman/docs/troubleshooting)) |

**Cost math:** If Desktop has \(D\) dirs and average branching \(b\), uncapped DFS is \(\Theta(\sum b^d)\). Caps + skip sets turn it into a **budgeted** walk.

---

## 5. Class C — Walk smarter (caches & monitors)

### 5.1 Git: untracked cache + fsmonitor (monorepo class)

**Problem:** `git status` ≈ refresh tracked paths + discover untracked dirs ([gitperf Ch.7](https://gitperf.com/chapter-07.html)).

| Accelerator | Data structure / algorithm | Measured effect (Hostetler / Git-for-Windows discussions) |
|-------------|----------------------------|-----------------------------------------------------------|
| **Untracked cache** | Index extension: cache **directory mtimes**; skip unchanged dirs when hunting untracked | ~2× alone on large trees |
| **FSMonitor** | Daemon listens to OS events; Git queries “which paths changed?” instead of `lstat` all tracked files | Chromium ~393k files: status **970ms → 204ms** with FSMonitor; **→ ~40ms** with FSMonitor + untracked cache ([Hostetler writeups / InfoQ Git 2.37](https://www.infoq.com/news/2022/06/git-2-37-released/)) |
| **Complexity shift** | From **O(files in tree)** toward **O(recently changed files)** | Explicit goal of builtin FSMonitor ([git-for-windows discussion #3251](https://github.com/git-for-windows/git/discussions/3251)) |

OS backends: macOS **FSEvents**, Windows **ReadDirectoryChangesW** (builtin); Linux historically **Watchman**/inotify.

### 5.2 Watchman (Meta) — continuous watch, not per-command crawl

- Long-lived daemon; clients query “what changed since clock T”.  
- Failure mode: **recrawl** (expensive full tree) when OS event buffers overflow — mitigated by raising limits / watching fewer roots ([Watchman docs](https://facebook.github.io/watchman/docs/troubleshooting)).  
- **Debounce / coalesce** events so clients aren’t flooded.

### 5.3 Change journals vs directory notifications

| | Directory notify (FileSystemWatcher / RDCW) | USN journal |
|--|---------------------------------------------|-------------|
| While app down | Misses events → often **full rescan** | Can **replay** from last USN |
| Unit | Subtree | Volume |
| Overhead | Can stress pool memory if buffers huge ([Bruce Dawson / VsChromium](https://randomascii.wordpress.com/2018/04/17/making-windows-slower-part-1-file-access/)) | Async read of journal; Trail of Bits osquery `ntfs_journal_events` emphasizes non-blocking vs minifilter ([Security Boulevard](https://securityboulevard.com/2020/03/real-time-file-monitoring-on-windows-with-osquery/)) |

**Lesson:** Bigger watcher buffers ≠ faster; wrong buffer sizes can **slow the whole OS**. Prefer journals or modest buffers + “lost events → rescan subtree”.

---

## 6. Class D — Persist & stage work (product UX = algorithm)

### 6.1 Two-phase / progressive enrichment (CloneUp-relevant)

| Phase | Work | User-visible |
|-------|------|----------------|
| 1 | Cheap FS walk (names, mtimes, `.git` presence) | List appears in ~1–2s |
| 2 | Background `git status` / porcelain per repo | Dirty badges fill in |

This is the same **progressive disclosure of cost** pattern as: search engines show name hits before content; Everything keeps content search optional.

### 6.2 Desktop search products

| Product | Census | Update | Query |
|---------|--------|--------|-------|
| **Everything** | MFT | USN | Memory name index |
| **Windows Search** | Background crawler + filters | Incremental | DB; heavier, content-capable |
| **macOS Spotlight** | `mds`/`mdworker` | FSEvents-driven | Metadata store |

Common pattern: **pay once** for census, **amortize** with deltas, **never** block UI on full content indexing.

### 6.3 File managers (Files app, Explorer)

Large-folder freezes addressed by **async enumeration + keep UI pumping** (e.g. Files community PR #17682 on large-folder UI freezing). Algorithm here is often **producer/consumer queue** + virtualization, not a smarter disk format.

---

## 7. Data analysis angles (how teams decide what to optimize)

Representative measurement practice:

| Question | Method | Example |
|----------|--------|---------|
| Where does time go? | Trace2 / perf regions | Git: `refresh_index` vs `untracked` ([gitperf](https://gitperf.com/chapter-07.html)) |
| Is cache valid? | Probe FS mtime semantics | `git update-index --test-untracked-cache` |
| Are we event-starved? | Watchman recrawl warnings | Raise `max_user_watches` / reduce watches |
| Journal overflow? | Everything rebuilds after restart | Increase USN max size |
| UI jank? | Time-to-first-byte of list | Two-phase scan (CloneUp home) |

**Population-representative “classes” of users/workloads:**

1. **Consumer desktop search** (Everything-class) — millions of files, name queries  
2. **Dev monorepos** (Git + Watchman) — 10⁵–10⁶ tracked paths, frequent status  
3. **HPC / backup / scrub** — parallel tree walk over petabytes  
4. **App project pickers** (IDEs, CloneUp) — care about **project roots**, not every file  

Each class picks different points on the taxonomy (A–E).

---

## 8. Mapping to CloneUp home (actionable)

| CloneUp pain | Proven pattern | Suggested direction |
|--------------|----------------|---------------------|
| First paint blocked by `git status` × N repos | Two-phase enrich; Git fsmonitor for *inside* a repo | ✅ Done: fast scan + dirty worker |
| Walking all of Desktop | Root allowlist + depth cap + stop at `.git` | Tighten defaults; prefer recent ∪ user roots over whole Desktop |
| Expand “손댄 곳” | Bounded depth + skip sets + mtime top-K | ✅ `list_recent_child_paths` |
| Stale dirty badges | Event-driven refresh (USN/RDCW) or TTL re-probe selected row | Next: watch selected roots or refresh-on-focus |
| Want “Everything speed” globally | MFT+USN index (admin) | Optional advanced backend; not required for project picker |

**Do not** chase MFT for the default home list unless product accepts admin elevation and NTFS-only — for a GitHub helper, **budgeted walk + caches + monitors** match the Git/IDE class better than Everything-class.

---

## 9. Source shortlist (representative, not exhaustive)

| Domain | Source |
|--------|--------|
| Desktop search | [voidtools Everything FAQ](https://www.voidtools.com/faq/), [developer forum on MFT vs USN](https://www.voidtools.com/forum/viewtopic.php?t=12371) |
| Git | [High Performance Git Ch.7](https://gitperf.com/chapter-07.html), [InfoQ Git 2.37 FSMonitor](https://www.infoq.com/news/2022/06/git-2-37-released/), Hostetler / git-for-windows FSMonitor notes |
| Watchman | [facebook.github.io/watchman troubleshooting](https://facebook.github.io/watchman/docs/troubleshooting) |
| USN / Windows | Trail of Bits osquery USN article; Dawson “Making Windows Slower” (watcher buffer pathology) |
| Academic | USENIX FAST’18 full-path indexing; SC’12 parallel tree walk |
| Open MFT/USN engines | PulseFS, MFTIndexer, ntfs-reader |

---

## 10. One-page algorithm cheat sheet

```
if need_all_names_on_NTFS and can_elevate:
    index ← read_MFT(volume)
    forever: index.apply(read_USN(since))
elif need_project_roots_for_UI:
    roots ← allowlist ∪ recent_parents
    list ← walk(roots, max_depth, skip, stop_at_git)   # phase 1
    show(list)
    async: for repo in list.git: enrich(status)          # phase 2
elif need_repeated_git_status_on_huge_checkout:
    enable fsmonitor + untrackedCache
    status ← query(monitor) ∪ selective_stat
else:
    walk_with_budget + progressive_UI
```

---

*This note supports CloneUp home scanning design; it is research, not a commitment to ship MFT indexing.*
