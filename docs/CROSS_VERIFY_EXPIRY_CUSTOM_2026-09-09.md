# Cross-verify: Custom Expiration / Select date (2026-09-09)

Screenshot: `스크린샷 2026-09-09 195042.png`  
UI: GitHub classic PAT — Expiration **Custom…**, Select date **2026-09-10**, CloneUp still 「만료일을 읽는 중…」.

## Findings

| Check | Result |
|-------|--------|
| Ideal OCR text parse (`Select date *` + `2026-09-10`) | **PASS** → `2026-09-10` |
| Full-desktop screenshot WinOCR | **FAIL** — digits not read (`Select date *` seen; no `2026-09-10`) |
| Screenshot tip wording | Matches **pre-fix** copy (“키 만들기 창이…”) more than Custom tip → likely **0.1.14 install**, not `d8cfeee` source |
| Live Chrome UIA (same session) | **PASS** — date on **`Expiration` EditControl Value**, not on `Select date *` Text (empty) |
| Live hwnd OCR crop | **PASS** — reads ISO near Select date |

### UIA shape (Chrome classic, Custom + date chosen)

```
openers:  ListItem "Expiration"   (not "Custom…")
Select date *: TextControl, Value=""
Expiration:    EditControl, Value="YYYY-MM-DD"   ← actual date
```

So detection must use **Select date label present ⇒ Custom mode ⇒ read Expiration Edit value**, not only the Select date control’s Name/Value.

## Fixes after this verify

1. Prefer `Expiration` Edit ISO when `Select date *` label exists.
2. Green box: after scan miss, stop saying forever 「읽는 중」; show Custom/Select date hint.
3. OCR: wider band around Expiration/Select date when Select date is visible.

## Field effect

Needs **CloneUp app rebuild / Setup** (Path B is in the main GUI, not UM). Ask before build/release.
