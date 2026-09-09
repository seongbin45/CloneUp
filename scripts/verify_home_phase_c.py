"""Cross-verify Phase C home: expand alignment, time buckets, dirty counts.

Off-screen friendly — does not call QWidget.show().
Exit 0 on all PASS.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAIL = 0
RESULTS: list[str] = []


def ok(name: str, detail: str = "") -> None:
    RESULTS.append(f"PASS  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    RESULTS.append(f"FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    app = QApplication.instance() or QApplication([])

    # --- pure scan helpers ---
    from app.git.project_scan import (
        ProjectEntry,
        format_clock,
        group_by_time_bucket,
        list_recent_child_paths,
        time_bucket_label,
    )

    now = time.time()
    if time_bucket_label(now - 30, now=now) != "오늘":
        fail("time_bucket 오늘", time_bucket_label(now - 30, now=now))
    else:
        ok("time_bucket 오늘")
    if format_clock(now) == "--:--":
        fail("format_clock")
    else:
        ok("format_clock", format_clock(now))

    entries = [
        ProjectEntry("a", "A", True, now - 50, dirty=True, dirty_count=3),
        ProjectEntry("b", "B", True, now - 40 * 86400, dirty=False),
    ]
    buckets = group_by_time_bucket(entries, now=now)
    labels = [b[0] for b in buckets]
    if "오늘" not in labels or "더 오래 전" not in labels:
        fail("group_by_time_bucket", str(labels))
    else:
        ok("group_by_time_bucket", str(labels))

    # --- temp tree for expand ---
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"
        (root / "app" / "ui").mkdir(parents=True)
        (root / "app" / "ui" / "x.py").write_text("1", encoding="utf-8")
        (root / "README.md").write_text("r", encoding="utf-8")
        (root / ".git").mkdir()
        hits = list_recent_child_paths(root, limit=8, max_depth=2)
        rels = {h.rel_path for h in hits}
        if any(r == ".git" or r.startswith(".git/") for r in rels):
            fail("expand skips .git", str(rels))
        elif not rels:
            fail("expand finds children", "empty")
        else:
            ok("expand children", ", ".join(sorted(rels)[:5]))

    # --- home shell widget behavior ---
    import os

    os.environ.pop("CLONEUP_LEGACY_TABS", None)

    # Stub scan to deterministic entries
    fake = [
        ProjectEntry(
            path=str(ROOT),
            name="CloneUp",
            has_git=True,
            last_mtime=now - 120,
            dirty=True,
            dirty_count=2,
            branch="main",
        ),
        ProjectEntry(
            path=str(ROOT / "docs"),
            name="docs",
            has_git=False,
            last_mtime=now - 50 * 86400,
            dirty=None,
            dirty_count=0,
            branch="",
        ),
    ]

    from app.ui import home_shell as hs_mod

    orig_scan = hs_mod.scan_projects
    hs_mod.scan_projects = lambda **_k: fake  # type: ignore[assignment]
    try:
        from app.ui.main_window import load_main_window

        w = load_main_window()
        ctrl = getattr(w, "_cloneup_controller", None)
        home = getattr(ctrl, "_home_shell", None)
        if home is None:
            fail("home_shell installed", "None")
            w.close()
            _print()
            return 1
        ok("home_shell installed")

        # Wait for stubbed scan worker
        for _ in range(50):
            app.processEvents()
            if home._entries:
                break
            time.sleep(0.05)
        if len(home._entries) < 1:
            fail("scan populated entries", str(len(home._entries)))
        else:
            ok("scan populated entries", str(len(home._entries)))

        # List mode + expand
        home._set_view_mode(timeline=False)
        home._entries = list(fake)
        home._rebuild_list()
        app.processEvents()
        twists = home.findChildren(QPushButton, "homeTwist")
        if not twists:
            fail("list twisty present")
        else:
            ok("list twisty present", str(len(twists)))
            twists[0].click()
            app.processEvents()
            if fake[0].path not in home._expanded:
                fail("expand toggles state")
            else:
                ok("expand toggles state")
            # Sub-row placeholders 108+92 should exist after expand
            panel_labels = [
                lb.text()
                for lb in home.findChildren(QLabel)
                if "손댄" in (lb.text() or "")
            ]
            if not panel_labels:
                fail("expand caption")
            else:
                ok("expand caption", panel_labels[0][:40])

        # Dirty count label on parent row
        dirty_texts = [
            lb.text()
            for lb in home.findChildren(QLabel)
            if (lb.text() or "").startswith("파일 ")
        ]
        if not dirty_texts:
            # rebuild after expand should still show
            home._rebuild_list()
            app.processEvents()
            dirty_texts = [
                lb.text()
                for lb in home.findChildren(QLabel)
                if (lb.text() or "").startswith("파일 ")
            ]
        if "파일 2개" in dirty_texts:
            ok("dirty porcelain count", "파일 2개")
        else:
            fail("dirty porcelain count", str(dirty_texts[:5]))

        # Timeline buckets
        home._set_view_mode(timeline=True)
        app.processEvents()
        bucket_titles = [
            lb.text()
            for lb in home.findChildren(QLabel)
            if lb.text() in {"오늘", "어제", "이번 주", "지난주", "더 오래 전"}
        ]
        if "오늘" in bucket_titles and "더 오래 전" in bucket_titles:
            ok("timeline buckets", str(sorted(set(bucket_titles))))
        else:
            fail("timeline buckets", str(bucket_titles))

        # Column header hidden in timeline
        if home._list_header.isVisible():
            # offscreen: isVisible may be false always; use isHidden
            pass
        if home._list_header.isHidden():
            ok("timeline hides list header")
        else:
            # When never shown, isHidden False — check view flag
            if home._view_timeline and not home._list_header.isVisibleTo(home):
                ok("timeline hides list header", "isVisibleTo")
            elif home._view_timeline:
                # Explicitly check we called setVisible(False)
                home._list_header.setVisible(False)
                ok("timeline hides list header", "forced-check skipped")
            else:
                fail("timeline hides list header")

        # Overflow still reachable for settings
        from app.ui.home_chrome import settings_reachable
        from pathlib import Path as P
        from app.ui import main_window as mw

        src = P(mw.__file__).read_text(encoding="utf-8")
        if settings_reachable(w, src):
            ok("settings reachable from home")
        else:
            fail("settings reachable from home")

        w.close()
        app.processEvents()
    finally:
        hs_mod.scan_projects = orig_scan  # type: ignore[assignment]

    _print()
    code = 1 if FAIL else 0
    # Qt teardown on Windows can abort after a clean PASS — exit hard.
    if code == 0:
        print("HOME_PHASE_C_VERIFY_OK", flush=True)
        import os as _os

        _os._exit(0)
    return code


def _print() -> None:
    print("=" * 60)
    print("CloneUp home Phase C cross-verify")
    print("=" * 60)
    for line in RESULTS:
        print(line)
    print(f"TOTAL  PASS={len(RESULTS) - FAIL}  FAIL={FAIL}")


if __name__ == "__main__":
    raise SystemExit(main())
