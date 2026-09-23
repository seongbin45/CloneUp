"""Verify home-scan heavy-root + enrich gates (rev. 7.1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.git.project_scan import (
        DIRTY_ENRICH_CAP,
        DIRTY_SELECT_DEBOUNCE_MS,
        DIRTY_TTL_SEC,
        DEFAULT_SEED_MAX_DEPTH,
        HEAVY_CHILD_SCAN_LIMIT,
        HEAVY_CHILD_THRESHOLD,
        get_a_layer_state,
        is_heavy_scan_root,
        path_norm_key,
        resolve_scan_roots,
        scan_projects,
        select_dirty_enrich_paths,
    )
    from app.ui.settings_store import MAX_RECENT, load_recent_folders, load_scan_roots

    errors: list[str] = []

    if DIRTY_ENRICH_CAP != 8:
        errors.append(f"DIRTY_ENRICH_CAP={DIRTY_ENRICH_CAP} want 8")
    if DIRTY_TTL_SEC != 90:
        errors.append(f"DIRTY_TTL_SEC={DIRTY_TTL_SEC} want 90")
    if DIRTY_SELECT_DEBOUNCE_MS != 300:
        errors.append(f"DIRTY_SELECT_DEBOUNCE_MS={DIRTY_SELECT_DEBOUNCE_MS} want 300")
    if DEFAULT_SEED_MAX_DEPTH != 2:
        errors.append(f"DEFAULT_SEED_MAX_DEPTH={DEFAULT_SEED_MAX_DEPTH} want 2")
    if HEAVY_CHILD_THRESHOLD != 48:
        errors.append(f"HEAVY_CHILD_THRESHOLD={HEAVY_CHILD_THRESHOLD} want 48")
    if HEAVY_CHILD_SCAN_LIMIT != 48:
        errors.append(f"HEAVY_CHILD_SCAN_LIMIT={HEAVY_CHILD_SCAN_LIMIT} want 48")
    if MAX_RECENT != 12:
        errors.append(f"MAX_RECENT={MAX_RECENT} want 12 (settings)")

    a_keys, fail_closed = get_a_layer_state()
    print("a_layer_fail_closed", fail_closed, "n_keys", len(a_keys))
    if fail_closed:
        errors.append("A-layer unexpectedly fail-closed on this machine")
    elif len(a_keys) < 4:
        errors.append(f"A-layer expected 4 Known Folder keys, got {len(a_keys)}")
    else:
        for k in a_keys:
            if not is_heavy_scan_root(k):
                errors.append(f"A-layer key not heavy: {k}")

    roots = resolve_scan_roots()
    if load_recent_folders() and not load_scan_roots():
        for r in roots:
            if path_norm_key(r) in a_keys:
                errors.append(f"A-layer path used as hybrid walk root: {r}")

    entries, _partial = scan_projects(probe_dirty=False)
    git_n = sum(1 for e in entries if e.has_git)
    paths = select_dirty_enrich_paths(entries, cap=DIRTY_ENRICH_CAP)
    if len(paths) > DIRTY_ENRICH_CAP:
        errors.append(f"enrich paths {len(paths)} > K={DIRTY_ENRICH_CAP}")
    if git_n > DIRTY_ENRICH_CAP and len(paths) != DIRTY_ENRICH_CAP:
        errors.append(f"expected K={DIRTY_ENRICH_CAP} got {len(paths)} (git={git_n})")

    print("roots", len(roots), "projects", len(entries), "git", git_n)
    print("initial_enrich_n", len(paths), "MAX_RECENT", MAX_RECENT)
    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("OK rev.7.1 gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
