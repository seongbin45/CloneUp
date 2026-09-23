"""S0 baseline: home scan phase-1 / dirty-enrich wall times.

Usage (from repo root):
  python scripts/bench_home_scan.py
  python scripts/bench_home_scan.py --caps 8,12,16

Does not modify QSettings. Uses current recent/scan_roots unless --fixture-root.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bench CloneUp home scan cost (S0)")
    ap.add_argument(
        "--caps",
        default="8,12,16",
        help="Comma-separated dirty enrich caps to time (default 8,12,16)",
    )
    ap.add_argument(
        "--fixture-root",
        default="",
        help="If set, monkeypatch scan to this single root (ignore settings)",
    )
    ap.add_argument("--json-out", default="", help="Optional path to write JSON report")
    args = ap.parse_args()
    caps = [int(x.strip()) for x in args.caps.split(",") if x.strip()]

    from app.git import project_scan as ps
    from app.git.project_scan import (
        _probe_git_presence,
        default_scan_roots,
        resolve_scan_roots,
        scan_projects,
    )
    from app.ui.settings_store import load_recent_folders, load_scan_roots

    report: dict = {
        "case": "live_settings" if not args.fixture_root else "fixture_root",
        "recent": load_recent_folders(),
        "scan_roots_setting": load_scan_roots(),
    }

    if args.fixture_root:
        fr = Path(args.fixture_root).expanduser().resolve()
        ps.load_recent_folders = lambda: []  # type: ignore[method-assign]
        ps.load_scan_roots = lambda: [str(fr)]  # type: ignore[method-assign]
        # resolve_scan_roots reads load_scan_roots from settings_store at import
        # time binding — call scan with explicit roots instead.
        roots = [fr]
        report["roots"] = [str(fr)]
        report["n_roots"] = 1
        t0 = time.perf_counter()
        entries, _partial = scan_projects(roots=roots, probe_dirty=False)
        report["phase1_ms"] = _ms(t0)
    else:
        roots = resolve_scan_roots()
        report["roots"] = [str(r) for r in roots]
        report["n_roots"] = len(roots)
        report["default_scan_roots_preview"] = [str(r) for r in default_scan_roots()]
        t0 = time.perf_counter()
        entries, _partial = scan_projects(probe_dirty=False)
        report["phase1_ms"] = _ms(t0)

    git_paths = [e.path for e in entries if e.has_git]
    report["n_projects"] = len(entries)
    report["n_git"] = len(git_paths)

    # Full enrich (current home behavior)
    t0 = time.perf_counter()
    for p in git_paths:
        try:
            _probe_git_presence(Path(p))
        except Exception:
            pass
    report["enrich_all_ms"] = _ms(t0)
    report["enrich_all_n"] = len(git_paths)

    # Cap enrich: mtime-ranked like planned S2
    ranked = sorted(
        [e for e in entries if e.has_git],
        key=lambda e: e.last_mtime,
        reverse=True,
    )
    cap_rows = []
    for k in caps:
        subset = ranked[: max(0, k)]
        t0 = time.perf_counter()
        for e in subset:
            try:
                _probe_git_presence(Path(e.path))
            except Exception:
                pass
        row = {"k": k, "n": len(subset), "ms": _ms(t0)}
        if report["enrich_all_ms"] > 0 and len(git_paths) > 0:
            row["vs_all_pct"] = round(100.0 * row["ms"] / report["enrich_all_ms"], 1)
        cap_rows.append(row)
    report["enrich_caps"] = cap_rows

    # Human table
    print("=== CloneUp home scan S0 bench ===")
    print(f"case:           {report['case']}")
    print(f"n_roots:        {report['n_roots']}")
    for r in report["roots"]:
        print(f"  root: {r}")
    print(f"recent_count:   {len(report['recent'])}")
    print(f"phase1_ms:      {report['phase1_ms']}")
    print(f"n_projects:     {report['n_projects']}")
    print(f"n_git:          {report['n_git']}")
    print(f"enrich_all_ms:  {report['enrich_all_ms']}  (n={report['enrich_all_n']})")
    print("enrich by cap:")
    for row in cap_rows:
        extra = f"  ({row.get('vs_all_pct')}% of all)" if "vs_all_pct" in row else ""
        print(f"  K={row['k']}: {row['ms']} ms  n={row['n']}{extra}")

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
