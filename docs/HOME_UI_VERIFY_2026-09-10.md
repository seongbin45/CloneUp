# Home UI live verify (2026-09-10)

## Code fixes under test

1. `FactRow` / `FolderGlyph` take `colors=` / `home_chrome_colors()` (no direct `HOME_COLORS`)
2. Back/fwd: `QStyle.SP_ArrowBack/Forward` (no tofu chars)
3. Twist/⋯: `QFont.setFamilies([...])`
4. `_clear_layout`: `hide` + `setParent(None)` + `deleteLater`
5. QA: `CLONEUP_FORCE_THEME=dark|light` + `scripts/_launch_home_theme.py`

## Probes

| File | Content |
|------|---------|
| `%TEMP%\cloneup_theme_force_probe.txt` | `mode=dark pal=dark hc=HomeChromeColorsDark bg=#232019 text=#efeade` |
| `%TEMP%\cloneup_theme_applied.txt` | `applied=dark force=dark` |

## Pixel proof (forced dark)

Screenshot `2895e9f3-…-screenshot.png` (and siblings):

| Region | Dominant RGB | Mean luminance |
|--------|-------------:|---------------:|
| top bar | ~(32,32,32) | ~37 |
| sidebar | ~(35,32,25) ≈ `#232019`/`#1e1c16` | ~42 |
| list / detail | same dark browns | ~36 |

**Note:** Multimodal captions repeatedly mislabeled this as “light cream”. Trust pixels + probes, not the caption.

## A11y tree checks (dark force)

| Check | Result |
|-------|--------|
| `homeShell` / `homeBackBtn` | present |
| `FolderGlyph` on rows | present |
| noPick copy | `폴더를 하나 고르면 여기에서 바로 올리고 받을 수 있습니다.` |
| noPick FactRow widgets | absent (only empty host `QWidget`s) — ghost bars should be gone |
| Selected detail (earlier capture) | `FactRow` 위치 / GitHub / 공개 범위 / 안 올린 변경 |

## Light (OS / earlier source launch)

Selected CloneUp: facts readable, green CTAs, path with `/`, folder glyphs OK, back = style arrow (not tofu).

## How to re-verify locally

```bat
py -3 scripts/_launch_home_theme.py dark
py -3 scripts/_launch_home_theme.py light
```
