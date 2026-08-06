#!/usr/bin/env python3
"""
Export CloneUp terms (desin HTML) → installer license plain text (UTF-8 BOM).

Source of truth:
  desin/provision/CloneUp 이용약관.dc.html

Outputs:
  installer/license/CloneUp_Terms_ko.txt   (Inno Setup LicenseFile)
  legal/CloneUp_Terms_ko.txt               (repo copy / app bundle)

Run:
  .\\.venv\\Scripts\\python.exe scripts\\export_terms_license.py
"""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "desin" / "provision" / "CloneUp 이용약관.dc.html"
OUT_INSTALLER = ROOT / "installer" / "license" / "CloneUp_Terms_ko.txt"
OUT_LEGAL = ROOT / "legal" / "CloneUp_Terms_ko.txt"

# Design-only appendix (not shown on install license page)
_APPENDIX_MARKERS = (
    "부록 — 조항별 근거 교차검증",
    "부록 — 조항별",
    "조항별 근거 교차검증",
)


def extract_terms(html: str) -> str:
    # Drop tooling / styles / scripts
    t = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<helmet\b[^>]*>.*?</helmet>", " ", t)
    t = re.sub(r"(?is)<!--.*?-->", " ", t)

    # Cut design appendix (not the early mention of “부록에 정리”)
    cut = len(t)
    for marker in _APPENDIX_MARKERS:
        i = t.find(marker)
        if i != -1:
            cut = min(cut, i)
    t = t[:cut]

    # Block-ish tags → newlines
    t = re.sub(
        r"(?i)</?(h[1-6]|p|div|li|tr|section|article|br|ol|ul|table|thead|tbody)\b[^>]*>",
        "\n",
        t,
    )
    t = re.sub(r"(?i)<li\b[^>]*>", "\n  - ", t)
    # Remaining tags out
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    # Whitespace tidy
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # List lines: ensure "  - " form survives collapse
    lines: list[str] = []
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if s.startswith("- "):
            lines.append("  " + s)
        else:
            lines.append(s)
    body = "\n".join(lines).strip()
    return body + "\n"


def write_utf8_bom(path: Path, text: str) -> None:
    """Inno Setup Unicode license pages work best with UTF-8 BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))


def main() -> int:
    if not SRC.is_file():
        print(f"ERROR: missing source {SRC}", file=sys.stderr)
        return 1
    html = SRC.read_text(encoding="utf-8")
    body = extract_terms(html)
    if "제1조" not in body or "제19조" not in body:
        print(
            "ERROR: expected articles 1–19 missing — check HTML / extract logic",
            file=sys.stderr,
        )
        print(f"  length={len(body)} preview={body[:200]!r}", file=sys.stderr)
        return 1
    for dest in (OUT_INSTALLER, OUT_LEGAL):
        write_utf8_bom(dest, body)
        print(f"  wrote {dest.relative_to(ROOT)} ({dest.stat().st_size} bytes)")
    print("OK — re-run after editing the desin HTML.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
